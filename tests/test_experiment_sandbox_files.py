"""C23 actual local file boundary tests; stored Python is never executed."""
from dataclasses import FrozenInstanceError
import csv
import hashlib
import json
import os
import stat
import struct
from types import MappingProxyType
import zlib

import pytest
from sqlalchemy import create_engine, event

from db.app_models import AppBase
from orchestration.experiment_sandbox.contracts import (
    SandboxError, VerifiedEnvelope, verify_execution_envelope,
)
from orchestration.experiment_sandbox.files import (
    MAX_CELL_BYTES, MAX_CELLS, MAX_COLUMNS, MAX_LOG_BYTES, MAX_PIXELS, MAX_ROWS, StagedInputs,
    stage_inputs, validate_expected_outputs, validate_outputs, verify_staged_inputs,
)
from schema.research_experiments import MAX_OUTPUT_BYTES, content_sha256
from tests.research_experiment_support import make_experiment_fixture


def declaration(name='summary.json', kind='table'):
    return {'name': name, 'kind': kind, 'description': 'Explicitly synthetic output'}


def table(**changes):
    return json.dumps({'columns': ['value'], 'rows': [[1]], **changes}, ensure_ascii=False).encode()


@pytest.fixture(scope='module')
def verified(tmp_path_factory):
    directory = tmp_path_factory.mktemp('c23-files-actual-c22')
    sentinel = directory / 'must-not-execute'
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv('ENABLE_V1_CATALOGUE', 'true')
        patch.setenv('ENABLE_V1_INVESTIGATIONS', 'true')
        engine = create_engine('sqlite+pysqlite:///' + str(directory / 'synthetic.sqlite'))

        @event.listens_for(engine, 'connect')
        def foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')

        AppBase.metadata.create_all(engine)
        actual = make_experiment_fixture(engine, directory)
        request = actual.request()
        request['proposal']['python_code'] = f'from pathlib import Path\nPath({str(sentinel)!r}).write_text("bad")\n'
        experiment = actual.service.invoke('create', request, actual.user)['experiment']
        actual.service.invoke('approve', actual.decision(experiment), actual.user)
        dispatched = actual.service.invoke('dispatch', actual.decision(experiment), actual.user)['experiment']
        raw = actual.service.load_execution_envelope(dispatched['dispatch']['reservation_id'])
        result = verify_execution_envelope(raw, expected_envelope_sha256=content_sha256(raw['metadata']),
            environments={actual.environment.identity_sha256: actual.environment})
        yield result, sentinel
        assert not sentinel.exists()
        engine.dispose()


def forged_for_file_defense(envelope, **changes):
    """Defensive staging probes, not a replacement for C22 envelope admission."""
    copied = object.__new__(VerifiedEnvelope)
    for name in ('_metadata_json', '_files', 'envelope_sha256', 'job_id'):
        object.__setattr__(copied, name, changes.get(name, getattr(envelope, name)))
    return copied


def test_stage_actual_c22_exact_readonly_bytes_and_inert_code(verified, tmp_path):
    envelope, sentinel = verified
    staged = stage_inputs(tmp_path, envelope)
    assert isinstance(staged, StagedInputs)
    assert staged.root == tmp_path / envelope.job_id
    assert staged.code_path == staged.input_dir / 'analysis.py'
    assert staged.manifest_path == staged.input_dir / 'manifest.json'
    assert staged.code_path.read_bytes() == envelope.code
    assert staged.manifest_path.read_bytes() == envelope.manifest_bytes
    assert staged.total_bytes == envelope.input_size_bytes
    assert set(staged.input_dir.iterdir()) == {staged.input_dir / name for name in staged.content_pins}
    for name, raw in envelope.files.items():
        assert (staged.input_dir / name).read_bytes() == raw
    assert stat.S_IMODE(staged.root.stat().st_mode) == 0o700
    assert stat.S_IMODE(staged.input_dir.stat().st_mode) == 0o500
    for name, digest in staged.content_pins.items():
        path = staged.input_dir / name
        assert stat.S_IMODE(path.stat().st_mode) == 0o400
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert verify_staged_inputs(staged, envelope) is True
    assert stage_inputs(tmp_path, envelope) == staged
    assert not sentinel.exists()
    with pytest.raises(TypeError):
        staged.content_pins['analysis.py'] = 'bad'
    with pytest.raises(FrozenInstanceError):
        staged.total_bytes = 0


@pytest.mark.parametrize('name', ['analysis.py', 'manifest.json', '../escape', '/absolute', 'a/b', 'a\\b', '.hidden'])
def test_stage_rejects_reserved_or_escaping_input_names(verified, tmp_path, name):
    envelope, _ = verified
    forged = forged_for_file_defense(envelope, _files=MappingProxyType({**envelope.files, name: b'no execution'}))
    with pytest.raises(SandboxError):
        stage_inputs(tmp_path, forged)
    assert not (tmp_path / envelope.job_id).exists()


def test_stage_preserves_private_int64_bytes_defensively(verified, tmp_path):
    envelope, _ = verified
    raw = b'{"columns":["value"],"rows":[[9223372036854775807],[null],["\xe6\xb5\xb7"]]}'
    forged = forged_for_file_defense(envelope, _files=MappingProxyType({**envelope.files, 'private.json': raw}))
    staged = stage_inputs(tmp_path, forged)
    assert (staged.input_dir / 'private.json').read_bytes() == raw
    assert verify_staged_inputs(staged, forged)


def test_stage_input_budget_includes_code_and_manifest(verified, tmp_path):
    envelope, _ = verified
    metadata = envelope.metadata
    metadata['proposal']['resources']['max_input_bytes'] = envelope.input_size_bytes - 1
    forged = forged_for_file_defense(envelope, _metadata_json=json.dumps(metadata))
    with pytest.raises(SandboxError, match='sandbox_input_limit'):
        stage_inputs(tmp_path, forged)
    assert not (tmp_path / envelope.job_id).exists()


@pytest.mark.parametrize('attack', ['write', 'extra', 'symlink', 'hardlink', 'writable', 'parent_symlink', 'parent_public', 'partial'])
def test_staging_tamper_and_private_path_rejections(verified, tmp_path, attack):
    envelope, _ = verified
    parent = tmp_path
    if attack == 'parent_symlink':
        real = tmp_path / 'real'
        real.mkdir(mode=0o700)
        alias = tmp_path / 'alias'
        alias.symlink_to(real, target_is_directory=True)
        parent = alias
    elif attack == 'parent_public':
        parent.chmod(0o777)
    elif attack == 'partial':
        (parent / envelope.job_id).mkdir(mode=0o700)
    else:
        staged = stage_inputs(parent, envelope)
        staged.input_dir.chmod(0o700)
        if attack == 'write':
            staged.code_path.chmod(0o600)
            staged.code_path.write_bytes(b'changed')
            staged.code_path.chmod(0o400)
        elif attack == 'extra':
            (staged.input_dir / 'extra.json').write_bytes(b'{}')
        elif attack == 'symlink':
            staged.code_path.unlink()
            staged.code_path.symlink_to(staged.manifest_path)
        elif attack == 'hardlink':
            os.link(staged.code_path, parent / 'linked')
        elif attack == 'writable':
            staged.code_path.chmod(0o600)
        staged.input_dir.chmod(0o500)
    try:
        with pytest.raises(SandboxError):
            stage_inputs(parent, envelope)
    finally:
        if attack == 'parent_public':
            parent.chmod(0o700)


def test_verify_staged_allows_only_private_future_layout(verified, tmp_path):
    envelope, _ = verified
    staged = stage_inputs(tmp_path, envelope)
    for name in ('rootfs', 'outputs', 'scratch'):
        (staged.root / name).mkdir(mode=0o700)
    assert verify_staged_inputs(staged, envelope)
    (staged.root / 'unknown').mkdir(mode=0o700)
    with pytest.raises(SandboxError):
        verify_staged_inputs(staged, envelope)


@pytest.mark.parametrize('output', [declaration('unsafe.html'), declaration('unsafe.svg', 'raster'),
    declaration('unsafe.ipynb'), declaration('unsafe.pkl'), declaration('unsafe.zip'), declaration('unsafe.PNG', 'raster'),
    declaration('../unsafe.json'), declaration('/unsafe.json'), declaration('a/b.json'), declaration('a\\b.csv'),
    declaration('.hidden.json'), declaration('plot.png', 'table'), declaration('table.json', 'raster')])
def test_unsupported_declarations_fail_closed(output):
    with pytest.raises(SandboxError, match='sandbox_output_format'):
        validate_expected_outputs([output])


def test_output_declaration_duplicates_and_empty():
    for value in ([], [declaration(), declaration()], [declaration()] * 33, None):
        with pytest.raises(SandboxError):
            validate_expected_outputs(value)


def collect(tmp_path, raw, *, name='summary.json', kind='table', limit=MAX_OUTPUT_BYTES, logs=None):
    (tmp_path / name).write_bytes(raw)
    return validate_outputs(tmp_path, expected_outputs=[declaration(name, kind)], max_output_bytes=limit, logs=logs)


def test_validated_outputs_exact_int64_null_unicode_and_immutable(tmp_path):
    raw = table(columns=['value', 'label'], rows=[[9223372036854775807, '海'], [None, '=1+1'], [-0.5, '日本語']])
    result = collect(tmp_path, raw, logs={'stdout': b'\xff<untrusted>\n', 'stderr': b''})
    assert result.files['summary.json'] == raw
    assert result.logs['stdout'] == b'\xff<untrusted>\n'
    assert result.manifest['authority'] == 'experimental'
    assert result.manifest['scientific_approval'] == 'not_independently_verified'
    assert result.manifest['files'][0]['sha256'] == hashlib.sha256(raw).hexdigest()
    assert result.manifest['files'][0]['validation']['rows'] == 3
    assert result.total_bytes == len(raw) + sum(map(len, result.logs.values())) + len(result.manifest_bytes)
    detached = result.manifest
    detached['files'][0]['sha256'] = 'tamper'
    assert result.manifest['files'][0]['sha256'] != 'tamper'
    with pytest.raises(TypeError):
        result.files['summary.json'] = b'changed'
    with pytest.raises(FrozenInstanceError):
        result.total_bytes = 0


@pytest.mark.parametrize('raw', [b'{"columns":["x"],"rows":[[NaN]]}', b'{"columns":["x"],"rows":[[1e999]]}',
    b'{"columns":["x","x"],"rows":[]}', b'{"columns":["x"],"rows":[[1,2]]}',
    b'{"columns":["x"],"rows":[[{"value":1}]]}', b'{"columns":["x"],"rows":[[[1]]]}',
    b'{"columns":["x"],"rows":[],"rows":[]}', b'{"columns":["x"],"rows":[],"extra":1}',
    b'<script>alert(1)</script>', b'{"columns":["x"],"rows":[["\xff"]]}',
    b'{"columns":[],"rows":[]}', b'{"columns":[" "],"rows":[]}',
    table(rows=[['x' * (MAX_CELL_BYTES + 1)]]), b'[' * 1000 + b']' * 1000])
def test_invalid_json_table_rejected(tmp_path, raw):
    with pytest.raises(SandboxError, match='sandbox_output_format'):
        collect(tmp_path, raw)


def test_json_boundaries_and_empty_population(tmp_path):
    raw = table(rows=[['x' * MAX_CELL_BYTES]])
    assert collect(tmp_path, raw).files['summary.json'] == raw
    (tmp_path / 'summary.json').unlink()
    result = collect(tmp_path, table(rows=[]))
    assert result.manifest['files'][0]['validation']['rows'] == 0


def test_valid_csv_preserves_machine_formula_and_int64_bytes(tmp_path):
    raw = 'value,label\r\n9223372036854775807,"海\n日本"\r\n-1,=1+1\r\n'.encode()
    result = collect(tmp_path, raw, name='table.csv')
    assert result.files['table.csv'] == raw
    assert result.manifest['files'][0]['validation']['rows'] == 2


@pytest.mark.parametrize('raw', [b'', b'a,a\n1,2\n', b'a,b\n1\n', b'a\nx"y\n', b'a\n"x"z\n',
    b'a\n"unclosed\n', b'a\r1\r', b'a\n\x00\n', b'\xef\xbb\xbfa\n1\n', b'a\n\xff\n',
    ('a\n' + 'x' * (MAX_CELL_BYTES + 1)).encode()])
def test_invalid_csv_rejected(tmp_path, raw):
    with pytest.raises(SandboxError):
        collect(tmp_path, raw, name='table.csv')


@pytest.mark.parametrize('attack', ['delimiters', 'field', 'quoted_field', 'rows', 'cells'])
def test_csv_preparse_budget_rejects_before_reader_allocation(tmp_path, monkeypatch, attack):
    if attack == 'delimiters':
        raw = b',' * 100_000 + b'\n'
    elif attack == 'field':
        raw = b'value\n' + b'x' * (MAX_CELL_BYTES + 1) + b'\n'
    elif attack == 'quoted_field':
        raw = b'value\n"' + b'""' * (MAX_CELL_BYTES + 1) + b'"\n'
    elif attack == 'rows':
        raw = b'value\n' + b'x\n' * (MAX_ROWS + 1)
    else:
        header = ','.join(f'c{number}' for number in range(MAX_COLUMNS)).encode() + b'\n'
        row = b','.join([b'x'] * MAX_COLUMNS) + b'\n'
        raw = header + row * (MAX_CELLS // MAX_COLUMNS + 1)

    def forbidden_reader(*args, **kwargs):
        raise AssertionError('Over-budget CSV must refuse before allocating reader records')

    monkeypatch.setattr(csv, 'reader', forbidden_reader)
    with pytest.raises(SandboxError, match='sandbox_output_format'):
        collect(tmp_path, raw, name='table.csv')


@pytest.mark.parametrize('value', ['"' * MAX_CELL_BYTES,
    '海' * (MAX_CELL_BYTES // 3) + 'x' * (MAX_CELL_BYTES % 3),
    'x' * (MAX_CELL_BYTES - 2) + '\r\n'])
def test_csv_preparse_counts_decoded_bytes_at_exact_bound(tmp_path, value):
    raw = ('value\n"' + value.replace('"', '""') + '"\n').encode('utf-8')
    assert len(value.encode('utf-8')) == MAX_CELL_BYTES
    result = collect(tmp_path, raw, name='table.csv')
    assert result.files['table.csv'] == raw
    assert result.manifest['files'][0]['validation'] == {
        'rows': 1, 'columns': 1,
        'machine_values': 'exact UTF-8 CSV strings; human CSV escaping is separate'}


def test_csv_preparse_quoted_newlines_are_not_record_boundaries(tmp_path):
    raw = b'value\n"a\nb"\n"c\r\nd"\n'
    result = collect(tmp_path, raw, name='table.csv')
    assert result.files['table.csv'] == raw
    assert result.manifest['files'][0]['validation']['rows'] == 2


def chunk(kind, raw):
    return struct.pack('>I', len(raw)) + kind + raw + struct.pack('>I', zlib.crc32(kind + raw) & 0xffffffff)


def png(*, width=2, height=1, color=2, bits=8, interlace=0, pixels=None, extra=b''):
    channels = {0: 1, 2: 3, 6: 4}.get(color, 3)
    pixels = pixels if pixels is not None else b'\x00' + b'\x10' * width * channels
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, bits, color, 0, 0, interlace))
            + extra + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))


@pytest.mark.parametrize('color', [0, 2, 6])
def test_png_strict_raster_profile_valid(color, tmp_path):
    raw = png(color=color)
    result = collect(tmp_path, raw, name='plot.png', kind='raster')
    assert result.files['plot.png'] == raw
    assert result.manifest['files'][0]['validation']['width'] == 2
    assert result.manifest['files'][0]['validation']['channels'] == {0: 1, 2: 3, 6: 4}[color]


@pytest.mark.parametrize('raw', [b'<svg></svg>', png()[:-1], png() + b'extra', png(bits=16), png(color=3),
    png(interlace=1), png(width=0), png(width=4097), png(width=4096, height=MAX_PIXELS // 4096 + 1),
    png(pixels=b'\x05' + b'\x00' * 6), png(pixels=b'\x00' * 1000),
    png(extra=chunk(b'tEXt', b'html\x00<script>')), png(extra=chunk(b'acTL', b'\x00' * 8)),
    png()[:29] + b'\xff' + png()[30:]])
def test_png_malformed_unsafe_and_bomb_rejected(tmp_path, raw):
    with pytest.raises(SandboxError, match='sandbox_output_format'):
        collect(tmp_path, raw, name='plot.png', kind='raster')


@pytest.mark.parametrize('attack', ['symlink', 'hardlink', 'fifo', 'directory', 'extra', 'missing', 'directory_symlink'])
def test_output_filesystem_attacks_do_not_block(tmp_path, attack):
    output = tmp_path / 'output'
    output.mkdir(mode=0o700)
    target = output / 'summary.json'
    if attack == 'symlink':
        (tmp_path / 'source').write_bytes(table())
        target.symlink_to(tmp_path / 'source')
    elif attack == 'hardlink':
        (tmp_path / 'source').write_bytes(table())
        os.link(tmp_path / 'source', target)
    elif attack == 'fifo':
        os.mkfifo(target)
    elif attack == 'directory':
        target.mkdir()
    elif attack == 'extra':
        target.write_bytes(table())
        (output / 'extra.py').write_bytes(b'never execute')
    elif attack == 'directory_symlink':
        output.rmdir()
        output.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(SandboxError):
        validate_outputs(output, expected_outputs=[declaration()], max_output_bytes=MAX_OUTPUT_BYTES)


def test_output_aggregate_counts_logs_and_manifest(tmp_path):
    raw = table()
    result = collect(tmp_path, raw, logs={'stdout': b'log'})
    with pytest.raises(SandboxError, match='sandbox_output_limit'):
        validate_outputs(tmp_path, expected_outputs=[declaration()], max_output_bytes=result.total_bytes - 1, logs={'stdout': b'log'})
    assert validate_outputs(tmp_path, expected_outputs=[declaration()], max_output_bytes=result.total_bytes,
                            logs={'stdout': b'log'}).total_bytes == result.total_bytes
    with pytest.raises(SandboxError):
        validate_outputs(tmp_path, expected_outputs=[declaration()], max_output_bytes=MAX_OUTPUT_BYTES,
                         logs={'stdout': b'x' * (MAX_LOG_BYTES + 1)})
    with pytest.raises(SandboxError):
        validate_outputs(tmp_path, expected_outputs=[declaration()], max_output_bytes=MAX_OUTPUT_BYTES, logs={'other': b'bad'})


@pytest.mark.parametrize('limit', [True, 0, -1, MAX_OUTPUT_BYTES + 1, 1.5])
def test_invalid_output_limits(tmp_path, limit):
    with pytest.raises(SandboxError):
        validate_outputs(tmp_path, expected_outputs=[declaration()], max_output_bytes=limit)


def test_file_replacement_during_read_rejected(tmp_path, monkeypatch):
    target = tmp_path / 'summary.json'
    target.write_bytes(table())
    read = os.read
    changed = False

    def replace(fd, size):
        nonlocal changed
        result = read(fd, size)
        if not changed and stat.S_ISREG(os.fstat(fd).st_mode):
            changed = True
            replacement = tmp_path / 'replacement'
            replacement.write_bytes(table(rows=[[2]]))
            replacement.replace(target)
        return result

    monkeypatch.setattr(os, 'read', replace)
    with pytest.raises(SandboxError, match='sandbox_file_changed'):
        validate_outputs(tmp_path, expected_outputs=[declaration()], max_output_bytes=MAX_OUTPUT_BYTES)


def test_output_directory_replacement_during_read_rejected(tmp_path, monkeypatch):
    output = tmp_path / 'output'
    output.mkdir(mode=0o700)
    (output / 'summary.json').write_bytes(table())
    read = os.read
    changed = False

    def replace(fd, size):
        nonlocal changed
        result = read(fd, size)
        if not changed and stat.S_ISREG(os.fstat(fd).st_mode):
            changed = True
            output.rename(tmp_path / 'old-output')
            output.mkdir(mode=0o700)
            (output / 'summary.json').write_bytes(table(rows=[[2]]))
        return result

    monkeypatch.setattr(os, 'read', replace)
    with pytest.raises(SandboxError, match='sandbox_file_changed'):
        validate_outputs(output, expected_outputs=[declaration()], max_output_bytes=MAX_OUTPUT_BYTES)


def test_output_directory_enumeration_stops_before_full_untrusted_listing(tmp_path, monkeypatch):
    (tmp_path / 'summary.json').write_bytes(table())
    for number in range(100):
        (tmp_path / f'extra-{number}.json').write_bytes(b'{}')
    scandir = os.scandir
    observed = []

    class BoundedEntries:
        def __init__(self, directory):
            self.entries = scandir(directory)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.entries.close()

        def __iter__(self):
            return self

        def __next__(self):
            entry = next(self.entries)
            observed.append(entry.name)
            assert len(observed) <= 2  # one declared name plus one rejection
            return entry

    def no_whole_listing(*_):
        raise AssertionError('Unbounded directory listing is forbidden')

    monkeypatch.setattr(os, 'scandir', BoundedEntries)
    monkeypatch.setattr(os, 'listdir', no_whole_listing)
    with pytest.raises(SandboxError, match='sandbox_directory_limit'):
        validate_outputs(tmp_path, expected_outputs=[declaration()], max_output_bytes=MAX_OUTPUT_BYTES)
    assert len(observed) == 2


def test_reused_inputs_reject_large_unexpected_inode_population(verified, tmp_path):
    envelope, _ = verified
    staged = stage_inputs(tmp_path, envelope)
    staged.input_dir.chmod(0o700)
    for number in range(100):
        (staged.input_dir / f'extra-{number}.json').write_bytes(b'{}')
    staged.input_dir.chmod(0o500)
    with pytest.raises(SandboxError, match='sandbox_directory_limit'):
        stage_inputs(tmp_path, envelope)
