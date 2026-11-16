"""Bounded private semantic inputs; current bytes and authority are never cached.

Only the trusted host shares this instance. Every lookup verifies owned bytes,
binds the manifest/transport generation, and returns detached primitive frames.
Current namespace, policy and closing fences remain the caller/store's work.
"""
from collections import OrderedDict
from concurrent.futures import Future
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import sys
from threading import Condition, RLock

import pandas as pd
from pydantic import BaseModel

from ingestion import edna_catalogue_inputs as inputs
from ingestion.immutable_bundle import canonical_bytes
from schema.catalogue_snapshot import manifest_id, validated_manifest


@dataclass(frozen=True)
class _Validated:
    value: inputs.DatasetInputs
    decoded: int
    rows: int
    accounted_bytes: int


def _detached(value):
    tables = {}
    for name, frame in value.tables.items():
        copy = frame.copy(deep=True)
        # Index storage is otherwise shared by pandas even with deep=True.
        if isinstance(frame.index, pd.RangeIndex):
            copy.index = pd.RangeIndex(frame.index.start, frame.index.stop,
                frame.index.step, name=deepcopy(frame.index.name))
        else:
            copy.index = pd.Index(frame.index.to_numpy(copy=True), copy=True,
                name=deepcopy(frame.index.name))
        copy.columns = pd.Index(frame.columns.to_numpy(copy=True), copy=True,
            name=deepcopy(frame.columns.name))
        copy.attrs = deepcopy(frame.attrs)
        tables[name] = copy
    return inputs.DatasetInputs(value.metadata.model_copy(deep=True), tables,
        tuple(obj.model_copy(deep=True) for obj in value.objects))


def _metadata_bytes(value, seen=None):
    seen = set() if seen is None else seen
    if id(value) in seen:
        return 0
    seen.add(id(value))
    total = sys.getsizeof(value)
    if isinstance(value, BaseModel):
        total += _metadata_bytes(vars(value), seen)
        total += _metadata_bytes(value.__pydantic_fields_set__, seen)
    elif isinstance(value, dict):
        total += sum(_metadata_bytes(k, seen) + _metadata_bytes(v, seen) for k, v in value.items())
    elif isinstance(value, (tuple, list, set, frozenset)):
        total += sum(_metadata_bytes(item, seen) for item in value)
    return total


def _retained(value):
    # pandas deep accounting intentionally overcounts shared immutable strings.
    size = _metadata_bytes((value.metadata, value.objects)) + 4096
    for frame in value.tables.values():
        size += int(frame.memory_usage(index=True, deep=True).sum())
        size += int(frame.columns.memory_usage(deep=True)) + _metadata_bytes(frame.attrs) + 4096
    return _Validated(value, sum(int(f.attrs['decoded_bytes']) for f in value.tables.values()),
        sum(len(f) for f in value.tables.values()), size)


class ValidatedEDNAInputCache:
    def __init__(self, *, maximum_bytes=1024**3, maximum_entries=64, maximum_inflight=2):
        if (type(maximum_bytes) is not int or not 1 <= maximum_bytes <= 1024**3
                or type(maximum_entries) is not int or not 1 <= maximum_entries <= 64
                or type(maximum_inflight) is not int or not 1 <= maximum_inflight <= 4):
            raise ValueError('Explicit bounded eDNA semantic-input capacity required')
        self.maximum_bytes, self.maximum_entries = maximum_bytes, maximum_entries
        self.maximum_inflight = maximum_inflight
        self._entries, self._pending = OrderedDict(), {}
        self._condition = Condition(RLock())
        self._bytes = 0
        self._stats = dict(hits=0, misses=0, coalesced=0, evictions=0, failed_fills=0)

    def stats(self):
        with self._condition:
            return {**self._stats, 'entries': len(self._entries), 'inflight': len(self._pending),
                'accounted_retained_bytes': self._bytes}

    def load(self, manifest, contents, obj, *, decoded_budget=None, generation_binding=None):
        budget = inputs._decoded_budget(decoded_budget)
        if generation_binding is not None and (
                type(generation_binding) is not str or not inputs._SHA256.fullmatch(generation_binding)):
            raise ValueError('Exact validated input generation binding required')
        manifest = validated_manifest(manifest)
        if obj not in manifest.objects or (obj.role, obj.schema_version, obj.source_family) != (
                'canonical_rows', inputs.DATASET_VERSION, 'edna_metabarcoding'):
            raise ValueError('Frozen eDNA metadata role/schema/ownership mismatch')
        obj = next(item for item in manifest.objects if item.object_id == obj.object_id)
        metadata = inputs.dataset_metadata(inputs._verified_bytes(obj, contents))
        if (metadata.dataset_id, metadata.source_id) != (obj.dataset_id, obj.source_id):
            raise ValueError('Frozen eDNA metadata identity differs from sealed ownership')
        # Immutable bytes are verified even on hits and frozen before any wait.
        owned = {item.object_id: inputs._verified_bytes(item, contents)
            for item in manifest.objects if item.dataset_id == metadata.dataset_id}
        key = hashlib.sha256(canonical_bytes([
            'validated-c12-inputs-v1', manifest_id(manifest), obj.object_id,
            generation_binding, inputs.MAX_ROWS, inputs.MAX_DECODED_BYTES,
        ])).hexdigest()
        pending_key = key, budget
        owner = False
        with self._condition:
            while key not in self._entries and pending_key not in self._pending and len(self._pending) >= self.maximum_inflight:
                self._condition.wait()
            if key in self._entries:
                self._entries.move_to_end(key)
                validated = self._entries[key]
                self._stats['hits'] += 1
                pending = None
            elif pending_key in self._pending:
                pending = self._pending[pending_key]
                self._stats['coalesced'] += 1
            else:
                pending = Future()
                self._pending[pending_key] = pending
                self._stats['misses'] += 1
                owner = True
        if owner:
            try:
                # A cold fill passes remaining capacity to every decoder. Only
                # identical budgets coalesce; a narrow caller cannot fail another.
                value = inputs.load_dataset(manifest, owned, obj, decoded_budget=budget)
                validated = _retained(_detached(value))
                del value
            except BaseException as error:
                with self._condition:
                    self._pending.pop(pending_key)
                    self._stats['failed_fills'] += 1
                    pending.set_exception(error)
                    self._condition.notify_all()
                raise
            with self._condition:
                if key in self._entries:
                    validated = self._entries[key]
                    self._entries.move_to_end(key)
                elif validated.accounted_bytes <= self.maximum_bytes:
                    while self._entries and (len(self._entries) >= self.maximum_entries
                            or self._bytes + validated.accounted_bytes > self.maximum_bytes):
                        _, old = self._entries.popitem(last=False)
                        self._bytes -= old.accounted_bytes
                        self._stats['evictions'] += 1
                    self._entries[key] = validated
                    self._bytes += validated.accounted_bytes
                self._pending.pop(pending_key)
                pending.set_result(validated)
                self._condition.notify_all()
        elif pending is not None:
            validated = pending.result()
        if validated.decoded > budget or validated.rows > inputs.MAX_ROWS:
            raise ValueError('Frozen eDNA decoded/row budget exceeded')
        return _detached(validated.value)
