"""Bounded, revision-aware cache of verified public catalogue metadata only."""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from threading import RLock
import time

from sqlalchemy import text

import config
from ingestion.immutable_bundle import digest


class VerifiedCatalogueCache:
    def __init__(self, *, ttl=60, maximum=4, clock=time.monotonic):
        self.ttl, self.maximum, self.clock = ttl, maximum, clock
        self.entries = OrderedDict()
        self.lock = RLock()

    def clear(self):
        with self.lock:
            self.entries.clear()

    def get(self, load, revision):
        # The lock gives one refresh per process; no partially verified value is
        # visible to another request. Returned objects never alias stored values.
        with self.lock:
            try:
                key = revision()
            except Exception:
                self.entries.clear()
                return deepcopy(load()), {'state':'unverified_revision_miss', 'revision':None}
            saved = self.entries.get(key)
            if saved and self.clock() - saved[0] < self.ttl:
                self.entries.move_to_end(key)
                return deepcopy(saved[1]), {'state':'hit', 'revision':key}
            for _ in range(2):
                value = load()
                current = revision()
                if current == key:
                    self.entries[key] = (self.clock(), deepcopy(value))
                    self.entries.move_to_end(key)
                    while len(self.entries) > self.maximum:
                        self.entries.popitem(last=False)
                    return deepcopy(value), {'state':'miss', 'revision':key}
                key = current
            raise ValueError('Catalogue revisions changed during verification')


CACHE = VerifiedCatalogueCache()


def catalogue_revision():
    """Cheap public heads; full content/current-source checks remain in execution."""
    from ingestion.artifact_store import ArtifactStore
    from ingestion.edna_analysis_bundle import _registered_records
    from db.connection import get_engine

    pointers = []
    if config.EDNA_ARTIFACT_URI:
        store = ArtifactStore(config.EDNA_ARTIFACT_URI)
        for key in ('analysis/index.json', 'provisional-demos/index.json', 'regional-publications/current.json'):
            payload, generation = store.pointer(key)
            pointers.append([key, generation, payload])
    else:
        pointers = _registered_records()
    with get_engine().connect() as connection, connection.begin():
        connection.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        connection.exec_driver_sql("SET LOCAL statement_timeout='5s'")
        heads = [list(row) for row in connection.execute(text(
            'SELECT channel,generation_id,manifest_sha256 FROM corpus_publication ORDER BY channel LIMIT 101'))]
        registry = [list(row) for row in connection.execute(text(
            'SELECT registry_key,registry_id FROM research_registry_head ORDER BY registry_key LIMIT 101'))]
        if len(heads) > 100 or len(registry) > 100:
            raise ValueError('Catalogue revision head limit exceeded')
    contexts = []
    for folder, role in ((config.ANALYSIS_DIR, 'analysis'), (config.RELIABILITY_DIR, 'reliability')):
        path = Path(folder) / (role + '_documents.jsonl')
        content_hash = None
        if path.exists():
            # Bound reads even if a malformed local context file grows between
            # stat and open. A failed check follows the verified miss path.
            with path.open('rb') as stream:
                content = stream.read(16 * 1024 * 1024 + 1)
            if len(content) > 16 * 1024 * 1024:
                raise ValueError('Catalogue context revision exceeds size limit')
            content_hash = hashlib.sha256(content).hexdigest()
        contexts.append([str(path), content_hash])
    from preprocessing.edna_analysis import runtime_versions
    return digest([config.EDNA_ARTIFACT_URI, digest(config.DATABASE_URL), str(config.ANALYSIS_DIR), pointers, heads, registry,
                   contexts, runtime_versions(), 'auto-settings-v7', json.dumps(config.database_engine_options(), sort_keys=True)])
