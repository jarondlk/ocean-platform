"""C23 trusted file boundary; no Python execution or containment claim.

The caller must establish whole-job termination before ``validate_outputs``.
These checks neither stop a writer nor prove that a sandbox was contained.
Only deliberately bounded table/PNG profiles are supported. Exact machine
bytes are retained; any human spreadsheet export is a separate C07 operation.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
import csv
from dataclasses import dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
from types import MappingProxyType
import zlib

from orchestration.experiment_sandbox.contracts import SandboxError, VerifiedEnvelope
from schema.research_experiments import MAX_INPUT_BYTES, MAX_OUTPUT_BYTES

VERSION = 'c23-validated-outputs-v1'
MAX_ROWS = 100_000
MAX_COLUMNS = 128
MAX_CELLS = 1_000_000
MAX_CELL_BYTES = 16_384
MAX_LOG_BYTES = 1024 * 1024
MAX_PIXELS = 4_194_304
MAX_DIMENSION = 4096
_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$')
_INPUT_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$')
_JOB = re.compile(r'^c23-[a-f0-9]{48}$')
_RESERVED = frozenset({'analysis.py', 'manifest.json'})
_ROOT_DIRS = frozenset({'inputs', 'rootfs', 'outputs', 'scratch'})


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _limit(value, maximum, reason):
    if type(value) is not int or not 1 <= value <= maximum:
        raise SandboxError(reason)
    return value


def validate_expected_outputs(expected_outputs):
    """Reject unsupported declaration profiles before any future launch."""
    try:
        if type(expected_outputs) is not list or not 1 <= len(expected_outputs) <= 32:
            raise ValueError
        profiles = {}
        for declaration in expected_outputs:
            if not isinstance(declaration, Mapping) or not {'name', 'kind'} <= declaration.keys():
                raise ValueError
            name, kind = declaration['name'], declaration['kind']
            if type(name) is not str or not _NAME.fullmatch(name) or name in profiles:
                raise ValueError
            extension = Path(name).suffix
            if kind == 'table' and extension in {'.json', '.csv'}:
                profile = 'json-table-v1' if extension == '.json' else 'csv-table-v1'
            elif kind == 'raster' and extension == '.png':
                profile = 'png-rgb8-v1'
            else:
                raise ValueError
            profiles[name] = {'kind': kind, 'format': profile}
        return MappingProxyType({name: MappingProxyType(item) for name, item in sorted(profiles.items())})
    except (ValueError, TypeError, KeyError):
        raise SandboxError('sandbox_output_format') from None


def _absolute(path):
    value = Path(path)
    if '..' in value.parts or '\x00' in str(value):
        raise SandboxError('sandbox_path')
    value = value.absolute()
    if value.anchor != '/':
        raise SandboxError('sandbox_path')
    return value


def _open_directory_path(value, *, private):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    current = os.open('/', flags)
    try:
        for part in value.parts[1:]:
            child = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = child
        info = os.fstat(current)
        if not stat.S_ISDIR(info.st_mode) or (private and (info.st_uid != os.geteuid() or info.st_mode & 0o077)):
            raise SandboxError('sandbox_private_directory')
        return current
    except BaseException:
        os.close(current)
        raise


@contextmanager
def _directory(path, *, private=True):
    """Walk every component without following symlinks, retaining stable FDs."""
    value = _absolute(path)
    current = _open_directory_path(value, private=private)
    try:
        before = os.fstat(current)
        yield current, value
        after = _open_directory_path(value, private=private)
        try:
            named = os.fstat(after)
            if (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino):
                raise SandboxError('sandbox_file_changed')
        finally:
            os.close(after)
    finally:
        os.close(current)


def _child_directory(parent, name, *, private=True):
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    try:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or (private and (info.st_uid != os.geteuid() or info.st_mode & 0o077)):
            raise SandboxError('sandbox_private_directory')
        return fd
    except BaseException:
        os.close(fd)
        raise


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid, info.st_gid,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _names(directory, maximum):
    """Refuse unexpected inode populations before allocating a whole listing."""
    found = set()
    os.lseek(directory, 0, os.SEEK_SET)
    with os.scandir(directory) as entries:
        for entry in entries:
            found.add(entry.name)
            if len(found) > maximum:
                raise SandboxError('sandbox_directory_limit')
    return found


def _read_file(directory, name, maximum, *, read_only=False):
    # O_NONBLOCK ensures even a replaced FIFO cannot block the supervisor.
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > maximum
                or (read_only and (before.st_uid != os.geteuid() or before.st_mode & 0o222))):
            raise SandboxError('sandbox_file_integrity')
        parts, total = [], 0
        while True:
            chunk = os.read(fd, min(64 * 1024, maximum - total + 1))
            if not chunk:
                break
            parts.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise SandboxError('sandbox_output_limit')
        after = os.fstat(fd)
        named = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if _stamp(before) != _stamp(after) or _stamp(after) != _stamp(named) or total != before.st_size:
            raise SandboxError('sandbox_file_changed')
        return b''.join(parts)
    finally:
        os.close(fd)


def _write_file(directory, name, raw):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            if not count:
                raise SandboxError('sandbox_staging_unavailable')
            view = view[count:]
        os.fchmod(fd, 0o400)
        os.fsync(fd)
    finally:
        os.close(fd)


@dataclass(frozen=True)
class StagedInputs:
    root: Path
    input_dir: Path
    code_path: Path
    manifest_path: Path
    content_pins: Mapping
    total_bytes: int
    envelope_sha256: str

    def __post_init__(self):
        object.__setattr__(self, 'content_pins', MappingProxyType(dict(self.content_pins)))


def _input_payload(envelope):
    if not isinstance(envelope, VerifiedEnvelope) or not _JOB.fullmatch(envelope.job_id):
        raise SandboxError('sandbox_input_integrity')
    validate_expected_outputs(envelope.proposal['expected_outputs'])
    limit = _limit(envelope.resources['max_input_bytes'], MAX_INPUT_BYTES, 'sandbox_input_limit')
    copied = dict(envelope.files)
    if (not copied or len(copied) > 40 or any(type(name) is not str or not _INPUT_NAME.fullmatch(name)
            or name in _RESERVED or type(raw) is not bytes for name, raw in copied.items())):
        raise SandboxError('sandbox_input_integrity')
    copied.update({'analysis.py': envelope.code, 'manifest.json': envelope.manifest_bytes})
    if sum(map(len, copied.values())) > limit:
        raise SandboxError('sandbox_input_limit')
    return copied


def _verify_input_dir(root_fd, expected):
    entries = _names(root_fd, len(_ROOT_DIRS))
    if 'inputs' not in entries or not entries <= _ROOT_DIRS:
        raise SandboxError('sandbox_input_integrity')
    for entry in entries - {'inputs'}:
        fd = _child_directory(root_fd, entry)
        os.close(fd)
    fd = _child_directory(root_fd, 'inputs')
    try:
        if _names(fd, len(expected)) != set(expected) or os.fstat(fd).st_mode & 0o222:
            raise SandboxError('sandbox_input_integrity')
        for name, raw in expected.items():
            if _read_file(fd, name, len(raw), read_only=True) != raw:
                raise SandboxError('sandbox_input_integrity')
    finally:
        os.close(fd)


def stage_inputs(parent, envelope):
    """Create private pinned inputs; source code is copied, never interpreted.

    The parent must already exist and be owned/private. A failed partial stage
    remains quarantined and cannot be reused. No automatic deletion occurs.
    """
    try:
        expected = _input_payload(envelope)
        with _directory(parent) as (parent_fd, absolute):
            try:
                os.mkdir(envelope.job_id, 0o700, dir_fd=parent_fd)
                created = True
                os.fsync(parent_fd)
            except FileExistsError:
                created = False
            root_fd = _child_directory(parent_fd, envelope.job_id)
            try:
                if created:
                    os.mkdir('inputs', 0o700, dir_fd=root_fd)
                    input_fd = _child_directory(root_fd, 'inputs')
                    try:
                        for name, raw in sorted(expected.items()):
                            _write_file(input_fd, name, raw)
                        os.fchmod(input_fd, 0o500)
                        os.fsync(input_fd)
                    finally:
                        os.close(input_fd)
                    os.fsync(root_fd)
                _verify_input_dir(root_fd, expected)
                named = os.stat(envelope.job_id, dir_fd=parent_fd, follow_symlinks=False)
                if (named.st_dev, named.st_ino) != (os.fstat(root_fd).st_dev, os.fstat(root_fd).st_ino):
                    raise SandboxError('sandbox_file_changed')
            finally:
                os.close(root_fd)
        root = absolute / envelope.job_id
        return StagedInputs(root, root / 'inputs', root / 'inputs/analysis.py', root / 'inputs/manifest.json',
                            {name: _hash(raw) for name, raw in sorted(expected.items())},
                            sum(map(len, expected.values())), envelope.envelope_sha256)
    except SandboxError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise SandboxError('sandbox_staging_unavailable') from None


def verify_staged_inputs(staged, envelope):
    """Re-read exact pins immediately before a future trusted runtime create."""
    try:
        expected = _input_payload(envelope)
        if (not isinstance(staged, StagedInputs) or staged.root.name != envelope.job_id
                or staged.input_dir != staged.root / 'inputs' or staged.code_path != staged.input_dir / 'analysis.py'
                or staged.manifest_path != staged.input_dir / 'manifest.json'
                or staged.envelope_sha256 != envelope.envelope_sha256
                or dict(staged.content_pins) != {name: _hash(raw) for name, raw in sorted(expected.items())}
                or staged.total_bytes != sum(map(len, expected.values()))):
            raise SandboxError('sandbox_input_integrity')
        with _directory(staged.root) as (fd, _):
            _verify_input_dir(fd, expected)
        return True
    except SandboxError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise SandboxError('sandbox_input_integrity') from None


def _json_budget(raw):
    # Bound nesting, string tokens and structural node counts before allocation
    # by json.loads. These are safety-profile bounds, not silent sampling.
    depth = nodes = token = 0
    string = escape = False
    for byte in raw:
        if string:
            if byte == 34 and not escape:
                string = False
                token = 0
                continue
            token += 1
            if token > MAX_CELL_BYTES or byte < 32:
                raise ValueError
            if escape:
                escape = False
            elif byte == 92:
                escape = True
        elif byte == 34:
            string, token = True, 0
        elif byte in (91, 123):
            depth += 1
            nodes += 1
            token = 0
            if depth > 4:
                raise ValueError
        elif byte in (93, 125):
            depth -= 1
            token = 0
            if depth < 0:
                raise ValueError
        elif byte in (44, 58):
            nodes += 1
            token = 0
        elif byte not in (9, 10, 13, 32):
            token += 1
            if token > 128:
                raise ValueError
        if nodes > MAX_CELLS + 2 * MAX_ROWS + 2 * MAX_COLUMNS + 16:
            raise ValueError
    if string or depth:
        raise ValueError


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _constant(_):
    raise ValueError


def _json_table(raw):
    _json_budget(raw)
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=_object, parse_constant=_constant)
    if type(value) is not dict or set(value) != {'columns', 'rows'}:
        raise ValueError
    columns, rows = value['columns'], value['rows']
    _columns(columns)
    if type(rows) is not list or len(rows) > MAX_ROWS or len(rows) * len(columns) > MAX_CELLS:
        raise ValueError
    for row in rows:
        if type(row) is not list or len(row) != len(columns):
            raise ValueError
        for cell in row:
            if (type(cell) not in (str, int, float, bool, type(None))
                    or (type(cell) is float and not math.isfinite(cell))
                    or (type(cell) is str and len(cell.encode('utf-8')) > MAX_CELL_BYTES)):
                raise ValueError
    return {'rows': len(rows), 'columns': len(columns), 'machine_values': 'exact original bytes; no browser number conversion'}


def _columns(columns):
    if (type(columns) is not list or not 1 <= len(columns) <= MAX_COLUMNS
            or any(type(name) is not str or not name.strip() or len(name.encode('utf-8')) > MAX_CELL_BYTES for name in columns)
            or len(set(columns)) != len(columns)):
        raise ValueError


def _csv_budget(text):
    """Bound decoded cells and shape before csv.reader allocates a record.

    Quotes used as CSV syntax cost no decoded field bytes; doubled quotes cost
    one byte and quoted newlines remain field bytes, never new records.
    """
    quoted = closed = False
    start = True
    active = False
    field_bytes, fields = 0, 1
    columns, rows, cells = None, 0, 0
    index = 0

    def finish_record():
        nonlocal columns, rows, cells
        if not active:
            raise ValueError
        if columns is None:
            columns = fields
        else:
            rows += 1
            cells += fields
            if fields != columns or rows > MAX_ROWS or cells > MAX_CELLS:
                raise ValueError

    while index < len(text):
        char = text[index]
        decoded = False
        if quoted:
            if char == '"':
                if index + 1 < len(text) and text[index + 1] == '"':
                    index += 1
                    decoded = True
                else:
                    quoted, closed = False, True
            else:
                decoded = True
        elif char == '"':
            if not start or closed:
                raise ValueError
            quoted, start = True, False
            active = True
        elif char == ',':
            fields += 1
            if fields > MAX_COLUMNS:
                raise ValueError
            field_bytes, start, closed, active = 0, True, False, True
        elif char in '\n\r':
            if char == '\r':
                if index + 1 >= len(text) or text[index + 1] != '\n':
                    raise ValueError
                index += 1
            finish_record()
            field_bytes, fields = 0, 1
            start, closed, active = True, False, False
        elif closed:
            raise ValueError
        else:
            start = False
            active, decoded = True, True
        if decoded:
            scalar = ord(char)
            field_bytes += 1 if scalar < 0x80 else 2 if scalar < 0x800 else 3 if scalar < 0x10000 else 4
            if field_bytes > MAX_CELL_BYTES:
                raise ValueError
        index += 1
    if quoted:
        raise ValueError
    if active:
        finish_record()
    if columns is None:
        raise ValueError
    return rows, columns


def _csv_table(raw):
    text = raw.decode('utf-8')
    if '\x00' in text or text.startswith('\ufeff'):
        raise ValueError
    # csv.reader(strict=True) alone accepts quote characters in unquoted fields
    # and allocates an entire overwide record before a later shape check.
    expected_shape = _csv_budget(text)
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    columns = next(reader, None)
    _columns(columns)
    rows = 0
    for row in reader:
        rows += 1
        if (rows > MAX_ROWS or rows * len(columns) > MAX_CELLS or len(row) != len(columns)
                or any(len(cell.encode('utf-8')) > MAX_CELL_BYTES for cell in row)):
            raise ValueError
    if (rows, len(columns)) != expected_shape:
        raise ValueError
    return {'rows': rows, 'columns': len(columns), 'machine_values': 'exact UTF-8 CSV strings; human CSV escaping is separate'}


def _png(raw):
    if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError
    offset, header, compressed = 8, None, []
    ended = False
    while offset < len(raw):
        if len(raw) - offset < 12:
            raise ValueError
        size = struct.unpack('>I', raw[offset:offset + 4])[0]
        kind = raw[offset + 4:offset + 8]
        end = offset + 12 + size
        if end > len(raw) or size > MAX_OUTPUT_BYTES:
            raise ValueError
        data = raw[offset + 8:offset + 8 + size]
        crc = struct.unpack('>I', raw[offset + 8 + size:end])[0]
        if zlib.crc32(kind + data) & 0xffffffff != crc:
            raise ValueError
        if kind == b'IHDR':
            if header is not None or offset != 8 or size != 13:
                raise ValueError
            width, height, bits, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
            if (not 1 <= width <= MAX_DIMENSION or not 1 <= height <= MAX_DIMENSION
                    or width * height > MAX_PIXELS or bits != 8 or color not in (0, 2, 6)
                    or compression or filtering or interlace):
                raise ValueError
            header = (width, height, {0: 1, 2: 3, 6: 4}[color])
        elif kind == b'IDAT':
            if header is None or ended or len(compressed) >= 1024:
                raise ValueError
            compressed.append(data)
        elif kind == b'IEND':
            if header is None or not compressed or size or end != len(raw):
                raise ValueError
            ended = True
        else:
            # Reject all ancillary/animation/profile/text chunks in this initial
            # fixed subset. Broader raster support requires a reviewed profile.
            raise ValueError
        offset = end
    if not ended:
        raise ValueError
    width, height, channels = header
    stride, expected = width * channels + 1, (width * channels + 1) * height
    inflater = zlib.decompressobj()
    pixels = inflater.decompress(b''.join(compressed), expected + 1)
    if (len(pixels) != expected or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail
            or any(pixels[row * stride] > 4 for row in range(height))):
        raise ValueError
    return {'width': width, 'height': height, 'channels': channels, 'profile': 'noninterlaced 8-bit gray/RGB/RGBA; no ancillary chunks'}


@dataclass(frozen=True, init=False)
class ValidatedOutputs:
    _files: Mapping
    _logs: Mapping
    _manifest_json: bytes
    total_bytes: int

    def __init__(self, *args, **kwargs):
        raise TypeError('Use validate_outputs')

    @property
    def files(self):
        return self._files

    @property
    def logs(self):
        return self._logs

    @property
    def manifest(self):
        return json.loads(self._manifest_json)

    @property
    def manifest_bytes(self):
        return self._manifest_json


def validate_outputs(output_dir, *, expected_outputs, max_output_bytes, logs=None):
    """Collect from stable no-follow FDs after trusted whole-job termination.

    This validates bytes, not scientific correctness or current publication
    authority. It never executes returned code, HTML, notebooks or images.
    """
    try:
        limit = _limit(max_output_bytes, MAX_OUTPUT_BYTES, 'sandbox_output_limit')
        profiles = validate_expected_outputs(expected_outputs)
        retained_logs = dict(logs or {})
        if (not isinstance(logs, (Mapping, type(None))) or not set(retained_logs) <= {'stdout', 'stderr'}
                or any(type(raw) is not bytes or len(raw) > MAX_LOG_BYTES for raw in retained_logs.values())):
            raise SandboxError('sandbox_output_limit')
        total = sum(map(len, retained_logs.values()))
        if total > limit:
            raise SandboxError('sandbox_output_limit')
        retained, descriptors = {}, []
        with _directory(output_dir) as (directory, _):
            names_before = _names(directory, len(profiles))
            if names_before != set(profiles):
                raise SandboxError('sandbox_output_integrity')
            for name, profile in profiles.items():
                raw = _read_file(directory, name, limit - total)
                try:
                    validation = {'json-table-v1': _json_table, 'csv-table-v1': _csv_table, 'png-rgb8-v1': _png}[profile['format']](raw)
                except (ValueError, TypeError, UnicodeError, RecursionError, csv.Error, zlib.error, struct.error, StopIteration):
                    raise SandboxError('sandbox_output_format') from None
                retained[name] = raw
                total += len(raw)
                descriptors.append({'name': name, 'sha256': _hash(raw), 'size_bytes': len(raw), **profile, 'validation': validation})
            if _names(directory, len(profiles)) != names_before:
                raise SandboxError('sandbox_file_changed')
        manifest = {'version': VERSION, 'authority': 'experimental', 'scientific_approval': 'not_independently_verified',
            'files': descriptors, 'logs': [{'name': name, 'sha256': _hash(raw), 'size_bytes': len(raw),
                'capture_completeness': 'not_asserted'} for name, raw in sorted(retained_logs.items())]}
        manifest_bytes = _canonical(manifest)
        total += len(manifest_bytes)
        if total > limit:
            raise SandboxError('sandbox_output_limit')
        result = object.__new__(ValidatedOutputs)
        for name, value in {'_files': MappingProxyType(retained), '_logs': MappingProxyType(retained_logs),
                            '_manifest_json': manifest_bytes, 'total_bytes': total}.items():
            object.__setattr__(result, name, value)
        return result
    except SandboxError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise SandboxError('sandbox_output_integrity') from None
