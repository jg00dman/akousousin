# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""One loaded voice in its own process, speaking a run of text chunk by chunk with word timing.

Inference runs in a child process so the service stays responsive and a hung
voice can be killed. The child phonemizes and matches the whole run first (a
few milliseconds, no audio needed), then synthesises one chunk (a sentence, or
a clause of a long one) at a time and sends it with where each word is heard.
A chunk is sent only when the service is ready for it, because sending blocks
on the pipe; so synthesis stays just ahead of playback rather than racing
through a whole text.

Stopping sets a shared event that the child checks between chunks. A chunk
already being synthesised is allowed to finish and is discarded: reloading a
voice costs far more than finishing one chunk. Only a child that stops
answering is killed.
"""
import itertools
import logging
import multiprocessing as mp
import os
from multiprocessing.connection import wait
import threading
import time

from . import timeline

CHUNK_TIMEOUT = 60      # seconds for one chunk: longer means the voice has hung
STOP_GRACE = 5          # seconds for a stopped chunk to finish before the process is killed


def _samples_per_phoneme(voice, phonemes, ids, id_samples):
    """Audio samples for BOS, each phoneme and EOS, the way Piper groups phoneme ids; None if they don't line up."""
    from piper.voice import BOS, EOS, PAD
    pad = voice.config.phoneme_id_map.get(PAD, [])
    position, counts = 0, []
    for phoneme in itertools.chain([BOS], phonemes, [EOS]):
        expected = list(voice.config.phoneme_id_map.get(phoneme, []))
        if phoneme != EOS:
            expected += pad
        if ids[position:position + len(expected)] != expected:
            return None
        counts.append(int(sum(id_samples[position:position + len(expected)])))
        position += len(expected)
    return counts if position == len(ids) else None


def synthesize_chunk(voice, phonemes, config, timed):
    """PCM bytes for one chunk, as Piper's own synthesize() makes them, and samples per phoneme (or None)."""
    import numpy as np
    ids = voice.phonemes_to_ids(phonemes)
    result = voice.phoneme_ids_to_audio(ids, config, include_alignments=timed)
    audio, id_samples = result if isinstance(result, tuple) else (result, None)
    if config.normalize_audio:
        peak = np.max(np.abs(audio))
        audio = np.zeros_like(audio) if peak < 1e-8 else audio / peak
    if config.volume != 1.0:
        audio = audio * config.volume
    audio = np.clip(audio, -1.0, 1.0).astype(np.float32)
    pcm = np.clip(audio * 32767.0, -32767.0, 32767.0).astype(np.int16).tobytes()
    counts = None
    if id_samples is not None and len(id_samples) == len(ids):
        counts = _samples_per_phoneme(voice, phonemes, ids, id_samples)
    return pcm, counts


def plan(voice, text, events):
    """Chunks of phonemes for a run, and for each the owning token of every phoneme (None if not needed)."""
    sentences = [s for s in voice.phonemize(text) if s]
    pieces, starts = [], []
    for sentence in sentences:
        for index, piece in enumerate(timeline.chunks([sentence])):
            pieces.append(piece)
            starts.append(index == 0)  # this chunk begins a sentence
    if not events:
        return pieces, starts, [None] * len(pieces), []
    spans = timeline.tokens(text)
    words = [[] if timeline.silent(text[s:e]) else sum(voice.phonemize(text[s:e]), []) for s, e in spans]
    matcher = timeline.Matcher(words)
    owners = [matcher.chunk(piece) for piece in pieces]
    return pieces, starts, owners, spans


def sentence_ranges(starts, owners, spans):
    """For each chunk that begins a sentence, the text range of the whole sentence (None otherwise)."""
    ranges, current = [None] * len(starts), None
    for index, (begins, owned) in enumerate(zip(starts, owners)):
        if begins:
            current = index
        tokens = [owner for owner in owned or () if owner is not None]
        if current is not None and tokens:
            low, high = spans[min(tokens)][0], spans[max(tokens)][1]
            if ranges[current] is None:
                ranges[current] = (low, high)
            else:
                ranges[current] = (min(ranges[current][0], low), max(ranges[current][1], high))
    return ranges


def serve(pipe, model, stop):
    """The child process: load the voice, then speak runs as asked."""
    from piper import PiperVoice, SynthesisConfig
    try:
        voice = PiperVoice.load(model)
        timed = len(voice.session.get_outputs()) > 1
        pipe.send(('ready', voice.config.sample_rate, timed))
        while True:
            request = pipe.recv()
            config = SynthesisConfig(length_scale=request['length_scale'], volume=request.get('volume', 1),
                                     noise_scale=request.get('noise_scale', .667),
                                     noise_w_scale=request.get('noise_w_scale', .8))
            text, events = request['text'], request.get('events', False)
            pieces, starts, owners, spans = plan(voice, text, events)
            sentences = sentence_ranges(starts, owners, spans) if events else [None] * len(pieces)
            stopped = False
            for piece, begins, owned, sentence in zip(pieces, starts, owners, sentences):
                if stop.is_set():
                    stopped = True
                    break
                pcm, counts = synthesize_chunk(voice, piece, config, timed)
                described = _describe(text, spans, owned, counts, begins)
                if sentence:
                    described['sentence_range'] = timeline.trimmed(text, *sentence) or sentence
                pipe.send(('chunk', pcm, described))
            pipe.send(('stopped',) if stopped or stop.is_set() else ('done',))
    except (EOFError, BrokenPipeError, KeyboardInterrupt):
        pass
    except Exception:
        logging.exception('Inference failed')
        try:
            pipe.send(('failed', 'Inference failed'))
        except (EOFError, BrokenPipeError):
            pass
    finally:
        pipe.close()


def _describe(text, spans, owners, counts, begins):
    """What a chunk says: its words (text range and samples), the text it covers, whether it starts a sentence."""
    described = {'sentence': begins, 'words': [], 'covers': None}
    if owners is None:
        return described
    owned = sorted({owner for owner in owners if owner is not None})
    if owned:
        described['covers'] = (spans[owned[0]][0], spans[owned[-1]][1])
    if counts is not None:
        lead = counts[0]  # Piper's start marker sounds before the first phoneme
        for token, start, end in timeline.word_spans(owners, counts[1:-1]):
            trimmed = timeline.trimmed(text, *spans[token])
            if trimmed:
                described['words'].append((trimmed[0], trimmed[1], lead + start, lead + end))
    return described


class VoiceProcess:
    """The service's handle on one voice's process."""
    def __init__(self, model, target=serve, startup_timeout=60):
        self.model = str(model)
        self.target = target
        self.startup_timeout = startup_timeout
        self.process = self.pipe = None
        self.rate = self.timed = None
        self.stop = None
        self.busy = threading.Lock()

    def alive(self):
        return self.process is not None and self.process.is_alive()

    def start(self, cancelled=None):
        self.close()
        context = mp.get_context('spawn')
        self.stop = context.Event()
        self.pipe, child = context.Pipe()
        self.process = context.Process(target=self.target, args=(child, self.model, self.stop), daemon=True)
        self.process.start()
        child.close()
        try:
            message = self._receive(self.startup_timeout, cancelled)
            if message[0] != 'ready':
                raise RuntimeError('The voice could not be loaded')
            _, self.rate, self.timed = message
        except BaseException:
            self.close()
            raise

    def speak(self, request, cancelled):
        """Yield (pcm, description) for each chunk of a run until done or ``cancelled`` is set.

        Raises InterruptedError when stopped. The voice stays loaded unless it fails to stop.
        """
        if not self.busy.acquire(False):
            raise BlockingIOError('Voice is busy')
        try:
            if not self.alive():
                self.start(cancelled)
            self.stop.clear()
            self.pipe.send(request)
            while True:
                if cancelled.is_set():
                    self._halt()
                    raise InterruptedError('Speech cancelled')
                message = self._receive(CHUNK_TIMEOUT, cancelled, interruptible=True)
                if message is None:
                    continue  # cancelled while waiting: handled above
                kind = message[0]
                if kind == 'chunk':
                    yield message[1], message[2]
                elif kind == 'done':
                    return
                elif kind == 'stopped':
                    raise InterruptedError('Speech cancelled')
                else:
                    self.close()
                    raise RuntimeError('Speech synthesis failed')
        except GeneratorExit:
            self._halt()  # the caller stopped reading
            raise
        except InterruptedError:
            raise  # a stop, already handled; InterruptedError is also an OSError
        except (TimeoutError, EOFError, OSError):
            self.close()
            raise
        finally:
            self.busy.release()

    def _halt(self):
        """Stop the run in progress, keeping the voice loaded if it stops in time."""
        if not self.alive():
            return
        self.stop.set()
        deadline = time.monotonic() + STOP_GRACE
        try:
            while time.monotonic() < deadline:
                if self.pipe.poll(min(.5, max(0, deadline - time.monotonic()))):
                    if self.pipe.recv()[0] in ('done', 'stopped', 'failed'):
                        self.stop.clear()
                        return
        except (EOFError, OSError):
            pass
        logging.getLogger(__name__).warning('Voice did not stop in time; restarting it')
        self.close()

    def _receive(self, timeout, cancelled=None, interruptible=False):
        deadline = time.monotonic() + timeout
        while True:
            if cancelled is not None and cancelled.is_set():
                if interruptible:
                    return None
                raise InterruptedError('Cancelled while loading')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('The voice stopped responding')
            if hasattr(cancelled, 'fileno') and os.name != 'nt':
                # Sleep until the voice answers or the request is cancelled (waiting.Interrupt).
                if wait([self.pipe, cancelled], remaining):
                    if self.pipe.poll(0):
                        return self.pipe.recv()
            elif self.pipe.poll(min(.25, remaining)):  # a plain event has to be checked
                return self.pipe.recv()

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
        self.rate = self.timed = None
