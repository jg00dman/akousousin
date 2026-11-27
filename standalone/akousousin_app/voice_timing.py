# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Expose how long each phoneme lasts in a Piper voice, so speech can report where each word is heard.

Piper's model already decides how many audio frames each phoneme gets (its
``Ceil`` tensor, which feeds the decoder). Marking that tensor as a model output
gives exact per-phoneme timing at no extra cost. ONNX models are protobuf, and
marking an output is one small field added to the graph, so this needs no onnx
package:

* ModelProto.graph is field 7; GraphProto.node is field 1 (NodeProto output =
  field 2, op_type = field 4); GraphProto.output is field 12 (ValueInfoProto
  name = field 1).

Voices are patched on disk, once: a model patched in memory almost doubles the
memory of a loaded voice. Only files in Akousousin's own data folder are
changed; the checksum of the patched file is recorded beside the download's.
"""
import hashlib
import json
import logging
import mmap
import os
from pathlib import Path
import tempfile

_GRAPH, _NODE, _OUTPUT = 7, 1, 12
_NODE_OUTPUT, _NODE_TYPE, _VALUE_NAME = 2, 4, 1


def _varint(data, i):
    value = shift = 0
    while True:
        byte = data[i]
        i += 1
        value |= (byte & 0x7f) << shift
        if byte < 0x80:
            return value, i
        shift += 7
        if shift > 63:
            raise ValueError('Malformed varint')


def _encode(value):
    out = bytearray()
    while True:
        byte, value = value & 0x7f, value >> 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _fields(data, start=0, end=None):
    """(field number, wire type, key start, value start, value end) for each field in data[start:end]."""
    i, end = start, len(data) if end is None else end
    while i < end:
        key_start = i
        key, i = _varint(data, i)
        number, wire = key >> 3, key & 7
        if wire == 0:
            _, j = _varint(data, i)
        elif wire == 1:
            j = i + 8
        elif wire == 5:
            j = i + 4
        elif wire == 2:
            length, i = _varint(data, i)
            j = i + length
        else:
            raise ValueError(f'Unsupported protobuf wire type {wire}')
        if j > end:
            raise ValueError('Truncated model')
        yield number, wire, key_start, i, j
        i = j


def _graph(data):
    graphs = [field for field in _fields(data) if field[0] == _GRAPH and field[1] == 2]
    if len(graphs) != 1:
        raise ValueError('Expected one graph')
    return graphs[0]


def duration_tensor(data):
    """The name of the per-phoneme duration tensor, and whether the model already outputs it."""
    _, _, _, start, end = _graph(data)
    durations, outputs = [], set()
    for number, wire, _, value_start, value_end in _fields(data, start, end):
        if wire != 2:
            continue
        if number == _NODE:
            node_type, node_outputs = None, []
            for field, kind, _, s, e in _fields(data, value_start, value_end):
                if kind == 2 and field == _NODE_TYPE:
                    node_type = bytes(data[s:e])
                elif kind == 2 and field == _NODE_OUTPUT:
                    node_outputs.append(bytes(data[s:e]))
            if node_type == b'Ceil':
                durations.extend(node_outputs)
        elif number == _OUTPUT:
            for field, kind, _, s, e in _fields(data, value_start, value_end):
                if kind == 2 and field == _VALUE_NAME:
                    outputs.add(bytes(data[s:e]))
    if len(durations) != 1:
        raise ValueError(f'Expected one duration tensor, found {len(durations)}')
    return durations[0].decode(), durations[0] in outputs


def with_durations(data):
    """The model with its duration tensor added as an output; unchanged if it already is one."""
    name, exposed = duration_tensor(data)
    if exposed:
        return bytes(data)
    _, _, key_start, start, end = _graph(data)
    encoded = name.encode()
    value_info = bytes([_VALUE_NAME << 3 | 2]) + _encode(len(encoded)) + encoded
    graph = bytes(data[start:end]) + bytes([_OUTPUT << 3 | 2]) + _encode(len(value_info)) + value_info
    return bytes(data[:key_start]) + bytes([_GRAPH << 3 | 2]) + _encode(len(graph)) + graph + bytes(data[end:])


def timed(model):
    """Whether this model reports per-phoneme durations; False if it can't be read or patched."""
    try:
        with open(model, 'rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
            view = memoryview(mapped)
            try:
                return duration_tensor(view)[1]
            finally:
                view.release()
    except (OSError, ValueError, IndexError):
        return False


def ensure_timed(model, owned_root):
    """Make a voice report phoneme durations, patching its file once if it lies in our data folder.

    Returns True when the model reports durations. A voice that can't be patched
    (somewhere else on disk, read-only, or an unusual model) still works, just
    without word timing.
    """
    model = Path(model)
    try:
        if model.stat().st_size == 0:
            return False   # not a voice
        with open(model, 'rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
            view = memoryview(mapped)
            try:
                if duration_tensor(view)[1]:
                    return True
                if not _inside(model, owned_root):
                    return False
                patched = with_durations(view)
            finally:
                view.release()
        write_atomic(model, patched)
        record_checksum(model.parent / 'provenance.json', patched)
        logging.getLogger(__name__).info('Voice %s now reports word timing', model.name)
        return True
    except (OSError, ValueError, IndexError) as error:
        logging.getLogger(__name__).warning('Voice %s has no word timing: %s', model.name, error)
        return False


def _inside(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def write_atomic(path, data):
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def record_checksum(provenance, patched):
    """Note the patched file's checksum beside the downloaded one, so later checks accept either."""
    provenance = Path(provenance)
    if not provenance.is_file():
        return
    record = json.loads(provenance.read_text(encoding='utf-8'))
    record['timed_sha256'] = hashlib.sha256(patched).hexdigest()
    write_atomic(provenance, json.dumps(record, indent=2).encode())


def checksum_matches(actual, record):
    """Whether a voice file's checksum is the downloaded one or its timing-patched form."""
    return actual in (record.get('model_sha256'), record.get('timed_sha256'))
