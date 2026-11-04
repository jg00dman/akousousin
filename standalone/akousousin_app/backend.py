"""Multi-voice routing around the existing bounded Piper worker."""
import io
import json
import logging
import math
import hmac
from pathlib import Path
import threading
import wave

from akousousin_backend.server import Synthesizer, MAX_AUDIO, MAX_BODY
from . import settings


def worker(pipe, model):
    from piper import PiperVoice, SynthesisConfig
    try:
        voice = PiperVoice.load(model)
        pipe.send((True, voice.config.sample_rate))
        while True:
            request = pipe.recv()
            output = io.BytesIO()
            config = SynthesisConfig(length_scale=request['length_scale'], volume=request.get('volume', 1),
                                     noise_scale=request.get('noise_scale', .667),
                                     noise_w_scale=request.get('noise_w_scale', .8))
            with wave.open(output, 'wb') as wav:
                voice.synthesize_wav(request['text'], wav, syn_config=config)
            data = output.getvalue()
            if len(data) > MAX_AUDIO:
                raise ValueError('Audio exceeds limit')
            pipe.send((True, data))
    except (EOFError, BrokenPipeError):
        pass
    except Exception:
        logging.exception('Inference failed')
        try:
            pipe.send((False, 'Inference failed'))
        except (EOFError, BrokenPipeError):
            pass
    finally:
        pipe.close()


def resample(audio, target):
    import audioop  # Embedded Python 3.12; no external resampler or executable.
    with wave.open(io.BytesIO(audio), 'rb') as wav:
        rate = wav.getframerate()
        if rate == target:
            return audio
        pcm, _ = audioop.ratecv(wav.readframes(wav.getnframes()), 2, 1, rate, target, None)
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setparams((1, 2, target, 0, 'NONE', ''))
        wav.writeframes(pcm)
    return output.getvalue()


class Router:
    def __init__(self, path, target=worker):
        self.path = Path(path).resolve()
        self.target = target
        self.synth = None
        self.voice = None
        self.lock = threading.RLock()

    def choose(self, request, config):
        language = config['book_language'] or settings.language_for_lcid(request.get('language', 0))
        selected = config['language_voices'].get(language) if language else None
        return selected or request.get('voice') or config['voice']

    def start(self):
        config = settings.load(self.path)
        self.select(config['voice'], config)

    def select(self, selected, config):
        if selected not in config['voices']:
            raise RuntimeError('Selected voice is not installed')
        model = Path(config['voices'][selected]['path'])
        if not model.is_file() or not Path(str(model) + '.json').is_file():
            raise RuntimeError('Voice model/configuration is missing')
        if self.synth is None or self.voice != selected:
            self.close()
            self.synth = Synthesizer(model, target=self.target)
            self.synth.start()
            self.voice = selected

    def close(self):
        acquired = self.lock.acquire(timeout=.5)
        if not acquired:
            process = self.synth.process if self.synth else None
            try:
                if process:
                    process.terminate()
            except (ValueError, OSError):
                pass
            acquired = self.lock.acquire(timeout=4)
        if not acquired:
            return
        try:
            if self.synth:
                self.synth.close()
            self.synth = None
            self.voice = None
        finally:
            self.lock.release()

    def synthesize(self, request):
        if not self.lock.acquire(False):
            raise BlockingIOError('Piper is busy')
        try:
            config = settings.load(self.path)
            self.select(self.choose(request, config), config)
            options = {'text': request['text'], 'length_scale': request.get('length_scale', 1) / config['speed'],
                       'volume': config['volume'], 'noise_scale': config['noise_scale'],
                       'noise_w_scale': config['noise_w_scale']}
            audio = self.synth.synthesize(options)
            rate = request.get('sample_rate', self.synth.rate)
            return resample(audio, rate)
        finally:
            self.lock.release()


def application(router, instance, control="", stopping=None):
    def app(env, respond):
        status, kind = '200 OK', 'application/json'
        try:
            if env['PATH_INFO'] == '/health' and env['REQUEST_METHOD'] == 'GET':
                ready = router.synth is not None and router.synth.process is not None and router.synth.process.is_alive()
                body = json.dumps({'service': 'akousousin-piper', 'instance': instance, 'ready': ready,
                                   'settings': str(router.path), 'voice': router.voice}).encode()
                if not ready:
                    status = '503 Service Unavailable'
            elif env['PATH_INFO'] == '/shutdown' and env['REQUEST_METHOD'] == 'POST':
                if not control or not hmac.compare_digest(env.get('HTTP_X_AKOUSOUSIN_CONTROL', ''), control):
                    status, body = '403 Forbidden', b'{"error":"Not owned by this panel"}'
                else:
                    timer = threading.Timer(.5, stopping.set)
                    timer.daemon = True
                    timer.start()
                    body = b'{"stopping":true}'
            elif env['PATH_INFO'] == '/synthesize'  and env['REQUEST_METHOD'] == 'POST':
                size = int(env.get('CONTENT_LENGTH', '0'))
                if not 0 < size <= MAX_BODY:
                    raise ValueError('Request too large')
                request = json.loads(env['wsgi.input'].read(size))
                text, scale = request.get('text'), request.get('length_scale', 1)
                if not isinstance(text, str) or not text.strip() or len(text) > 16000:
                    raise ValueError('Invalid text')
                if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale):
                    raise ValueError('Invalid speed')
                if not .5 <= scale <= 2:
                    raise ValueError('Invalid speed')
                rate = request.get('sample_rate', 22050)
                if not isinstance(rate, int) or not 8000 <= rate <= 192000:
                    raise ValueError('Invalid sample rate')
                if 'language' in request and not isinstance(request['language'], int):
                    raise ValueError('Invalid language')
                body, kind = router.synthesize(request), 'audio/wav'
            else:
                status, body = '404 Not Found', b'{"error":"Not found"}'
        except (ValueError, TypeError, AttributeError):
            status, body = '400 Bad Request', b'{"error":"Invalid request"}'
        except BlockingIOError:
            status, body = '503 Service Unavailable', b'{"error":"Piper is busy"}'
        except TimeoutError:
            status, body = '504 Gateway Timeout', b'{"error":"Synthesis timed out"}'
        except Exception:
            logging.exception('Speech request failed')
            status, body = '503 Service Unavailable', b'{"error":"Voice unavailable"}'
        respond(status, [('Content-Type', kind), ('Content-Length', str(len(body)))])
        return [body]
    return app


def serve(path, instance, control_file):
    from waitress import create_server, wasyncore
    router = Router(path)
    config = settings.load(path)
    stopping = threading.Event()
    control = Path(control_file).read_text() if control_file else ''
    server = None
    try:
        router.start()
        server = create_server(application(router, instance, control, stopping), host='127.0.0.1',
                               port=config['port'], threads=4, connection_limit=16, backlog=8,
                               channel_timeout=70, max_request_body_size=MAX_BODY)
        while not stopping.is_set():
            wasyncore.loop(timeout=.1, count=1, map=server._map)
    finally:
        router.close()
        if server:
            for channel in list(server._map.values()):
                channel.close()
            server.task_dispatcher.shutdown(timeout=5)
