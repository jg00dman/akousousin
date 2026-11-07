# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Loopback-only WSGI service. Inference lives in a killable child process."""
import argparse
import io
import json
import logging
import math
import multiprocessing as mp
from pathlib import Path
import threading
import time
import wave

MAX_BODY = 65536
MAX_AUDIO = 64 * 1024 * 1024


def worker(pipe, model):
    # Import only in the inference process: HTTP remains responsive while loading.
    from piper import PiperVoice, SynthesisConfig
    try:
        voice = PiperVoice.load(model)
        pipe.send((True, voice.config.sample_rate))
        while True:
            request = pipe.recv()
            audio = io.BytesIO()
            with wave.open(audio, 'wb') as wav:
                voice.synthesize_wav(request['text'], wav,
                                     syn_config=SynthesisConfig(length_scale=request['length_scale']))
            data = audio.getvalue()
            if len(data) > MAX_AUDIO:
                raise ValueError('Audio exceeds size limit')
            pipe.send((True, data))
    except (EOFError, BrokenPipeError):
        pass
    except Exception:
        logging.exception('Piper inference failed')
        try:
            pipe.send((False, 'Piper inference failed'))
        except (EOFError, BrokenPipeError):
            pass
    finally:
        pipe.close()


class Synthesizer:
    def __init__(self, model, timeout=60, startup_timeout=60, target=worker):
        self.model = str(model)
        self.timeout = timeout
        self.startup_timeout = startup_timeout
        self.target = target
        self.process = self.pipe = None
        self.lock = threading.Lock()
        self.rate = None

    def close(self):
        if self.process is not None:
            self.process.terminate()
            self.process.join(2)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(2)
            self.process.close()
            self.process = None
        if self.pipe is not None:
            self.pipe.close()
            self.pipe = None
        self.rate = None

    def receive(self, timeout, cancelled=None):
        deadline = time.monotonic() + timeout
        while True:
            if cancelled is not None and cancelled.is_set():
                raise InterruptedError('Synthesis cancelled')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Piper response timed out')
            if self.pipe.poll(min(.05, remaining)):
                return self.pipe.recv()

    def start(self, cancelled=None):
        self.close()
        ctx = mp.get_context('spawn')
        self.pipe, child = ctx.Pipe()
        self.process = ctx.Process(target=self.target, args=(child, self.model), daemon=True)
        self.process.start()
        child.close()
        try:
            ok, self.rate = self.receive(self.startup_timeout, cancelled)
            if not ok:
                raise RuntimeError('Piper model loading failed')
        except BaseException:
            self.close()
            raise

    def synthesize(self, request, cancelled=None):
        # No unbounded synthesis queue. Health checks can use other WSGI threads.
        if not self.lock.acquire(blocking=False):
            raise BlockingIOError('Piper is busy')
        try:
            if self.process is None or not self.process.is_alive():
                self.start(cancelled)
            self.pipe.send(request)
            ok, audio = self.receive(self.timeout, cancelled)
            if not ok:
                raise RuntimeError('Piper synthesis failed')
            # Defend the HTTP boundary as well as validating again inside Wine.
            if len(audio) > MAX_AUDIO:
                raise ValueError('Audio exceeds size limit')
            with wave.open(io.BytesIO(audio), 'rb') as wav:
                if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, self.rate):
                    raise ValueError('Unexpected audio format')
                if wav.getnframes() == 0 or len(wav.readframes(wav.getnframes())) != wav.getnframes() * 2:
                    raise ValueError('Empty or truncated audio')
            return audio
        except BlockingIOError:
            raise
        except InterruptedError:
            # Screen readers frequently interrupt tiny utterances. If inference
            # is about to finish, discard its response but keep the loaded model.
            # A slow/hung worker still takes the bounded terminate/kill path.
            reusable = False
            if self.pipe is not None and self.process is not None:
                try:
                    if self.pipe.poll(.25):
                        response = self.pipe.recv()
                        reusable = bool(response[0]) and self.process.is_alive()
                except (EOFError, OSError, TypeError, IndexError):
                    pass
            if not reusable:
                self.close()
            raise
        except (ValueError, wave.Error) as error:
            self.close()
            raise RuntimeError("Invalid synthesized audio") from error
        except BaseException:
            self.close()
            raise
        finally:
            self.lock.release()


def application(synth, model, instance=''):
    def app(environ, start_response):
        status, mime = '200 OK', 'application/json'
        try:
            if environ['REQUEST_METHOD'] == 'GET' and environ['PATH_INFO'] == '/health':
                ready = synth.process is not None and synth.process.is_alive()
                status = '200 OK' if ready else '503 Service Unavailable'
                body = json.dumps({'service': 'akousousin-piper', 'ready': ready,
                                   'model': Path(model).name, 'sample_rate': synth.rate,
                                   'instance': instance}).encode()
            elif environ['REQUEST_METHOD'] == 'POST' and environ['PATH_INFO'] == '/synthesize':
                length = int(environ.get('CONTENT_LENGTH') or '0')
                if length <= 0 or length > MAX_BODY:
                    raise ValueError('Request must contain at most 65536 bytes')
                data = json.loads(environ['wsgi.input'].read(length))
                text = data.get('text')
                scale = data.get('length_scale', 1.0)
                if not isinstance(text, str) or not text.strip() or len(text) > 16000:
                    raise ValueError('Text must contain 1–16000 characters')
                if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale):
                    raise ValueError('Invalid length_scale')
                if not 0.5 <= scale <= 2.0:
                    raise ValueError('length_scale must be between 0.5 and 2')
                body = synth.synthesize({'text': text, 'length_scale': scale})
                mime = 'audio/wav'
            else:
                status, body = '404 Not Found', b'{"error":"Not found"}'
        except (ValueError, TypeError, AttributeError, json.JSONDecodeError):
            status, body = '400 Bad Request', b'{"error":"Invalid synthesis request"}'
        except BlockingIOError:
            status, body = '503 Service Unavailable', b'{"error":"Piper is busy"}'
        except TimeoutError:
            status, body = '504 Gateway Timeout', b'{"error":"Synthesis timed out"}'
        except Exception:
            logging.exception('Synthesis request failed')
            status, body = '503 Service Unavailable', b'{"error":"Piper unavailable"}'
        start_response(status, [('Content-Type', mime), ('Content-Length', str(len(body)))])
        return [body]
    return app


def main():
    mp.freeze_support()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--instance', default='')
    args = parser.parse_args()
    if not args.model.is_file() or not Path(str(args.model) + '.json').is_file():
        parser.error('Both the ONNX model and its .onnx.json configuration are required')
    if not 1 <= args.port <= 65535:
        parser.error('Invalid port')
    logging.basicConfig(level=logging.INFO)
    synth = Synthesizer(args.model)
    try:
        synth.start()
        from waitress import serve
        serve(application(synth, args.model, args.instance), host='127.0.0.1', port=args.port,
              threads=4, connection_limit=16, backlog=8, channel_timeout=70,
              max_request_body_size=MAX_BODY, clear_untrusted_proxy_headers=True)
    finally:
        synth.close()


if __name__ == '__main__':
    main()
