"""Read reuse with the real bounded GCS adapter and an inert provider fixture."""

from hashlib import sha256

from google.api_core.exceptions import Forbidden, NotFound, PreconditionFailed
import pytest

from ingestion.artifact_store import BoundedGcsStore
from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.retained_output_store import (
    RetainedOutputFile, RetainedOutputReader, _prefix,
)
from tests.test_experiment_sandbox_execution_store import binding


class Provider:
    def __init__(self):
        self.objects = {}
        self.metadata_requests = 0
        self.downloads = []
        self.fail_metadata = False
        self.replace_during_download = False
        self.oversized_response = False

    def bucket(self, _name):
        return self

    def blob(self, key):
        return Blob(self, key)


class Blob:
    def __init__(self, provider, key):
        self.provider, self.key = provider, key

    def reload(self):
        self.provider.metadata_requests += 1
        if self.provider.fail_metadata:
            raise Forbidden('provider fixture denied access')
        self.generation, data = self._live()
        self.size = len(data)

    def _live(self):
        try:
            return self.provider.objects[self.key]
        except KeyError:
            raise NotFound('object removed') from None

    def download_to_file(self, sink, *, if_generation_match, start, end, raw_download, checksum, retry):
        generation, data = self._live()
        if self.provider.replace_during_download:
            self.provider.objects[self.key] = (generation + 1, data)
            generation += 1
        if generation != if_generation_match:
            raise PreconditionFailed('generation changed')
        assert start == 0 and end == len(data) and raw_download and checksum is None and retry is None
        self.provider.downloads.append((self.key, generation, len(data)))
        sink.write(data + b'x' if self.provider.oversized_response else data)


def target(raw, identity, *, name='data.csv'):
    digest = sha256(raw).hexdigest()
    manifest = sha256(name.encode()).hexdigest()
    key = f'private/{_prefix(identity, manifest)}/files/{digest}'
    return manifest, key, RetainedOutputFile('output-fixture', name, 'table', 'text/csv', digest, len(raw))


def test_8_mib_output_transfer_reuses_one_verified_generation():
    provider = Provider()
    reader = RetainedOutputReader(BoundedGcsStore(bucket='fixture', prefix='private', client=provider))
    identity = binding()
    raw = b'a' * (8 * 1024 * 1024)
    manifest, key, file = target(raw, identity)
    provider.objects[key] = (1, raw)

    step = 256 * 1024
    data = b''.join(reader.read_file(identity, manifest, file)[offset:offset + step]
                    for offset in range(0, len(raw), step))
    assert reader.read_file(identity, manifest, file)[:1] == raw[:1]
    assert sha256(data).hexdigest() == file.sha256
    assert provider.metadata_requests == 33
    assert provider.downloads == [(key, 1, len(raw))]

    provider.objects[key] = (2, raw)
    assert reader.read_file(identity, manifest, file) == raw
    assert provider.downloads[-1] == (key, 2, len(raw))


@pytest.mark.parametrize('fault', ['missing', 'denied', 'size', 'corrupt', 'oversized-response', 'race'])
def test_cached_file_never_falls_back_to_stale_bytes(fault):
    provider = Provider()
    reader = RetainedOutputReader(BoundedGcsStore(bucket='fixture', prefix='private', client=provider))
    identity = binding()
    raw = b'column\nfixture\n'
    manifest, key, file = target(raw, identity)
    provider.objects[key] = (1, raw)
    assert reader.read_file(identity, manifest, file) == raw
    reason = 'sandbox_output_store_unavailable'
    if fault == 'missing':
        del provider.objects[key]
    elif fault == 'denied':
        provider.fail_metadata = True
    elif fault == 'size':
        reason = 'sandbox_output_store_integrity'
        provider.objects[key] = (1, raw + b'x')
    elif fault == 'corrupt':
        reason = 'sandbox_output_store_integrity'
        provider.objects[key] = (2, b'x' + raw[1:])
    elif fault == 'oversized-response':
        reason = 'sandbox_output_store_integrity'
        provider.objects[key] = (2, raw)
        provider.oversized_response = True
    else:
        provider.objects[key] = (2, raw)
        provider.replace_during_download = True

    with pytest.raises(SandboxError) as failure:
        reader.read_file(identity, manifest, file)
    assert failure.value.reason == reason

    provider.fail_metadata = provider.replace_during_download = provider.oversized_response = False
    provider.objects[key] = (4, raw)
    assert reader.read_file(identity, manifest, file) == raw
    assert provider.downloads[-1] == (key, 4, len(raw))


def test_cache_evicts_previous_file_when_switching_manifests():
    provider = Provider()
    reader = RetainedOutputReader(BoundedGcsStore(bucket='fixture', prefix='private', client=provider))
    identity = binding()
    raw = b'column\nfixture\n'
    targets = [target(raw, identity, name=name) for name in ('first.csv', 'other.csv')]
    for _, key, _ in targets:
        provider.objects[key] = (1, raw)
    for manifest, _, file in [*targets, targets[0]]:
        assert reader.read_file(identity, manifest, file) == raw
    assert [key for key, _, _ in provider.downloads] == [targets[0][1], targets[1][1], targets[0][1]]
