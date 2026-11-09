"""Explicit empty or sealed production catalogue authority for the beta.

Exact private activation, current lifecycle and current account policy bind
nonempty snapshots. Durable context mode adds reference-only C09 retention;
neither mode imports data, discovers sources or grants scientific approval.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
from contextlib import contextmanager
from contextvars import ContextVar
from threading import get_ident

from pydantic import TypeAdapter

from orchestration.catalogue_browser import CatalogueBrowser
from orchestration.catalogue_service import (
    CataloguePolicy, CatalogueService, CatalogueServiceError, FrozenCatalogueResolver,
    catalogue_access_binding,
)
from schema.context_catalogue import Identifier

PROJECT = "ocean-v1-beta-20261101"
VERSION = "ocean-v1-empty-catalogue-v1"
SOURCE_VERSION = "ocean-v1-gcs-catalogue-host-v1"
ACTIVATION_VERSION = "ocean-v1-catalogue-activation-v1"
MAX_ACTIVATION_BYTES = 256 * 1024
MAX_CONFIGURATION_BYTES = 4096
_identifier = TypeAdapter(Identifier)


class CatalogueHostConfigurationError(ValueError):
    """Fixed diagnostics; no filesystem contents or private inputs emitted."""


def _configuration_error():
    return CatalogueHostConfigurationError("Explicit immutable beta catalogue configuration required")


def _unavailable():
    return CatalogueServiceError("catalogue_unavailable", "Catalogue is unavailable", 503)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate configuration key")
        result[key] = value
    return result


def _signature(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
        value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


class _ConfigurationSource:
    def __init__(self, path, *, allow_test_owner=False):
        if allow_test_owner and os.environ.get("DEPLOYMENT_ENV") != "test":
            raise _configuration_error()
        self._test_owner = bool(allow_test_owner)
        self.path = Path(path)
        if not self.path.is_absolute() or ".." in self.path.parts or not self.path.name:
            raise _configuration_error()
        self.raw, self.signature = self._read()

    def _read(self):
        directory = descriptor = None
        try:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
            directory = os.open("/", flags)
            for part in self.path.parts[1:-1]:
                child = os.open(part, flags, dir_fd=directory)
                os.close(directory)
                directory = child
                parent = os.fstat(directory)
                if not self._test_owner and (parent.st_uid != 0 or parent.st_mode & 0o022):
                    raise ValueError("Untrusted configuration directory")
            descriptor = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                dir_fd=directory)
            before = os.fstat(descriptor)
            expected_owner = os.geteuid() if self._test_owner else 0
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != expected_owner
                    or stat.S_IMODE(before.st_mode) != 0o444 or before.st_nlink != 1
                    or not 0 < before.st_size <= MAX_CONFIGURATION_BYTES):
                raise ValueError("Untrusted configuration file")
            raw = os.read(descriptor, MAX_CONFIGURATION_BYTES + 1)
            after = os.fstat(descriptor)
            if len(raw) != before.st_size or _signature(before) != _signature(after):
                raise ValueError("Configuration changed while reading")
            return raw, _signature(after)
        except Exception:
            raise _configuration_error() from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if directory is not None:
                os.close(directory)

    def require_current(self):
        try:
            raw, signature = self._read()
            if raw != self.raw or signature != self.signature:
                raise ValueError("Catalogue authority changed")
        except Exception:
            raise _unavailable() from None


class _EmptyResolver:
    def __init__(self, source):
        self._source = source

    def resolve(self, user, snapshot_id):
        catalogue_access_binding(user)
        self._source.require_current()
        # No identifier belongs to this explicit zero-snapshot registry.
        raise CatalogueServiceError("not_found", "Catalogue object is unavailable", 404)


class _CurrentEmptyBrowser(CatalogueBrowser):
    def __init__(self, *, source, **kwargs):
        super().__init__(**kwargs)
        self._source = source

    def discover(self, payload, user):
        catalogue_access_binding(user)
        try:
            with self.service.read_scope():
                self._source.require_current()
                response = super().discover(payload, user)
                self._source.require_current()
                return response
        except CatalogueServiceError:
            raise
        except Exception:
            raise _unavailable() from None


def load_empty_catalogue(path, *, project_id, site_id, cursor_key, _allow_test_owner=False):
    """Return real C14/C16 services only for explicit immutable empty authority.

    The stable cursor key is supplied by the trusted host, never the JSON file.
    Only test-mode callers can admit an operator-owned temporary fixture path.
    Missing/malformed/changed authority never becomes a zero-inventory fallback.
    """
    try:
        if project_id != PROJECT or site_id != "v1:" + PROJECT:
            raise ValueError("Independent beta identity required")
        if type(cursor_key) is not bytes or len(cursor_key) < 32:
            raise ValueError("Stable host cursor key required")
        source = _ConfigurationSource(path, allow_test_owner=_allow_test_owner)
        document = json.loads(source.raw.decode("utf-8"), object_pairs_hook=_unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
        if (type(document) is not dict or set(document) != {
                "version", "project_id", "site_id", "revision", "snapshots"}
                or document["version"] != VERSION or document["project_id"] != PROJECT
                or document["site_id"] != site_id or type(document["snapshots"]) is not list
                or document["snapshots"]):
            raise ValueError("Explicit empty registry required")
        revision = _identifier.validate_python(document["revision"], strict=True)
        service = CatalogueService(resolver=_EmptyResolver(source))
        browser = _CurrentEmptyBrowser(source=source, service=service, snapshots=(),
            permitted=lambda user, descriptor: False, revision=revision, cursor_key=cursor_key)
        source.require_current()
        return service, browser
    except Exception:
        raise _configuration_error() from None


def _canonical(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _document(raw):
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite catalogue JSON")))


def _source_binding(source, project_id, site_id):
    import re
    document = _document(source.raw)
    if (project_id != PROJECT or site_id != "v1:" + PROJECT
            or type(document) is not dict or set(document) != {
                "version", "project_id", "site_id", "bucket", "prefix",
                "activation_object", "activation_sha256"}
            or document["version"] != SOURCE_VERSION or document["project_id"] != PROJECT
            or document["site_id"] != site_id or document["bucket"] != PROJECT + "-snapshots"
            or document["prefix"] != "v1/catalogue"
            or type(document["activation_sha256"]) is not str
            or not re.fullmatch(r"[a-f0-9]{64}", document["activation_sha256"])
            or document["activation_object"] != "v1/catalogue/activations/"
                + document["activation_sha256"] + ".json"
            or _canonical(document) != source.raw):
        raise _configuration_error()
    return document


class _ActivationAuthority:
    def __init__(self, source, binding, store):
        self.source, self.binding, self.store = source, binding, store
        self.initial = self._read()
        self._scope = ContextVar("catalogue_activation_scope", default=None)

    def _read(self):
        self.source.require_current()
        value = self.store.read(self.binding["activation_object"], max_bytes=MAX_ACTIVATION_BYTES)
        if (type(value.data) is not bytes or not 0 < len(value.data) <= MAX_ACTIVATION_BYTES
                or type(value.generation) is not int or value.generation < 1
                or hashlib.sha256(value.data).hexdigest() != self.binding["activation_sha256"]):
            raise _unavailable()
        return value

    def require_current(self):
        scope = self._scope.get()
        if scope and scope["active"] and scope["thread"] == get_ident():
            self.source.require_current()
            return
        self._verify_current()

    def _verify_current(self):
        try:
            value = self._read()
            if value.data != self.initial.data or value.generation != self.initial.generation:
                raise ValueError("Activation authority replaced")
        except Exception:
            raise _unavailable() from None

    @contextmanager
    def read_scope(self):
        scope = self._scope.get()
        if scope and scope["active"] and scope["thread"] == get_ident():
            yield
            return
        self._verify_current()
        scope = {"active": True, "thread": get_ident()}
        token = self._scope.set(scope)
        try:
            yield
            self._verify_current()
        finally:
            scope["active"] = False
            self._scope.reset(token)


def _activation(raw, *, research_enabled=False):
    from orchestration.catalogue_registration import ScientificCatalogueRegistration
    from schema.catalogue_browser import CatalogueSnapshotDescriptor
    from schema.scientific_catalogue import DatasetBinding
    document = _document(raw)
    if (type(research_enabled) is not bool or type(document) is not dict or set(document) != {
            "version", "project_id", "site_id", "policy_revision", "authorization_ref",
            "access", "scientific_mode", "scientific_approval", "research_enabled",
            "snapshots", "qualifications"}
            or document["version"] != ACTIVATION_VERSION or document["project_id"] != PROJECT
            or document["site_id"] != "v1:" + PROJECT
            or document["access"] != {"roles": ["admin"], "account_types": ["internal"]}
            or document["scientific_mode"] != "datasets_only"
            or document["scientific_approval"] is not False or document["research_enabled"] is not research_enabled
            or type(document["authorization_ref"]) is not str
            or not 1 <= len(document["authorization_ref"]) <= 4096
            or type(document["snapshots"]) is not list or not 1 <= len(document["snapshots"]) <= 128
            or type(document["qualifications"]) is not list
            or not 1 <= len(document["qualifications"]) <= 32
            or any(type(v) is not str or not 1 <= len(v) <= 4096 for v in document["qualifications"])
            or _canonical(document) != raw):
        raise _configuration_error()
    _identifier.validate_python(document["policy_revision"], strict=True)
    descriptors, registrations, datasets, registration_ids = [], {}, {}, set()
    for entry in document["snapshots"]:
        if type(entry) is not dict or set(entry) != {"descriptor", "registration", "datasets"}:
            raise _configuration_error()
        descriptor = CatalogueSnapshotDescriptor.model_validate(entry["descriptor"])
        values = entry["registration"]
        if (type(values) is not dict or set(values) != {
                "snapshot_id", "child_snapshot_ids", "references", "registration_id"}
                or type(values["child_snapshot_ids"]) is not list
                or not 1 <= len(values["child_snapshot_ids"]) <= 128
                or type(values["references"]) is not list
                or len(values["references"]) != len(values["child_snapshot_ids"]) + 1
                or any(type(v) is not list or len(v) != 2 or any(type(s) is not str for s in v)
                    for v in values["references"])
                or type(entry["datasets"]) is not list or not 1 <= len(entry["datasets"]) <= 4000):
            raise _configuration_error()
        registration = ScientificCatalogueRegistration(snapshot_id=values["snapshot_id"],
            child_snapshot_ids=tuple(values["child_snapshot_ids"]),
            references=tuple(tuple(v) for v in values["references"]),
            registration_id=values["registration_id"])
        if (registration.snapshot_id != descriptor.snapshot_id
                or descriptor.snapshot_id in registrations or registration.registration_id in registration_ids):
            raise _configuration_error()
        bindings = tuple(DatasetBinding.model_validate(item) for item in entry["datasets"])
        if (len({item.dataset_id for item in bindings}) != len(bindings)
                or {item.snapshot_id for item in bindings} != set(registration.child_snapshot_ids)):
            raise _configuration_error()
        registrations[descriptor.snapshot_id] = registration
        registration_ids.add(registration.registration_id)
        descriptors.append(descriptor)
        datasets[descriptor.snapshot_id] = bindings
    return document, tuple(descriptors), registrations, datasets


class _CurrentSnapshotResolver(FrozenCatalogueResolver):
    def __init__(self, *, authority, **kwargs):
        super().__init__(**kwargs)
        self.authority = authority

    @contextmanager
    def request_scope(self):
        with self.authority.read_scope(), self.store.read_scope():
            yield

    def _authorization_state(self, user, snapshot_id):
        catalogue_access_binding(user)
        if user.role != "admin" or user.account_type != "internal":
            raise CatalogueServiceError("not_found", "Catalogue object is unavailable", 404)
        self.authority.require_current()
        return super()._authorization_state(user, snapshot_id)


def load_snapshot_catalogue(path, *, project_id, site_id, cursor_key,
                            context_retention=False, research_retention=False, _allow_test_owner=False, _test_store=None):
    """Bind explicit sealed GCS sources; never populate or modify their store.

    The image contains only an opaque hash/address. Scientific data and source
    policy remain in the private bucket. Current registration/lifecycle, source
    integrity and the current DB account are enforced before catalogue access.
    """
    try:
        from ingestion.artifact_store import BoundedGcsStore
        from ingestion.gcs_catalogue_snapshot import GcsCatalogueSnapshotStore
        from ingestion.scientific_catalogue_inputs import load_registry
        from schema.catalogue_snapshot import manifest_id
        if type(context_retention) is not bool or type(research_retention) is not bool or research_retention and not context_retention:
            raise ValueError("Explicit context-retention selection required")
        if type(cursor_key) is not bytes or len(cursor_key) < 32:
            raise ValueError("Stable cursor key required")
        if _test_store is not None and os.environ.get("DEPLOYMENT_ENV") != "test":
            raise ValueError("Test store requires explicit test mode")
        source = _ConfigurationSource(path, allow_test_owner=_allow_test_owner)
        binding = _source_binding(source, project_id, site_id)
        object_store = _test_store if _test_store is not None else BoundedGcsStore(
            bucket=binding["bucket"], prefix="")
        authority = _ActivationAuthority(source, binding, object_store)
        document, descriptors, registrations, datasets = _activation(authority.initial.data,
            research_enabled=research_retention)
        allowed_snapshots = {identity for registration in registrations.values()
            for identity in (registration.snapshot_id, *registration.child_snapshot_ids)}

        def access_gate(manifest):
            authority.require_current()
            return manifest_id(manifest) in allowed_snapshots

        kwargs = {"_test_store": _test_store} if _test_store is not None else {}
        store_type = GcsCatalogueSnapshotStore
        if context_retention:
            from ingestion.beta_catalogue_retention import BetaCatalogueRetentionStore
            store_type = BetaCatalogueRetentionStore
            if research_retention:
                from ingestion.beta_catalogue_retention import BetaResearchRetentionStore
                store_type = BetaResearchRetentionStore
        store = store_type(bucket=binding["bucket"], prefix=binding["prefix"],
            access_gate=access_gate, **kwargs)
        for identity, registration in registrations.items():
            registration.require_current(store)
            registry = load_registry(*store.read(identity)).metadata
            if (tuple(registry.datasets) != datasets[identity] or registry.analyses or registry.workflows
                    or registry.definitions or registry.relationships or registry.superseded_generations):
                raise ValueError("Exact datasets-only scientific index required")

        def permitted(user, descriptor):
            authority.require_current()
            return user.role == "admin" and user.account_type == "internal"

        def policy(user, identity):
            authority.require_current()
            allowed = {(item.snapshot_id, item.dataset_id, item.source_id, item.source_family)
                for item in datasets[identity]}

            def eligible(snapshot, metadata):
                authority.require_current()
                return (user.role == "admin" and user.account_type == "internal"
                    and (snapshot, metadata.dataset_id, metadata.source_id, metadata.family) in allowed)

            return CataloguePolicy(revision=document["policy_revision"], dataset_eligible=eligible,
                scientific_eligible=lambda snapshot, item: False)

        catalogue = CatalogueService(resolver=_CurrentSnapshotResolver(authority=authority,
            store=store, policy_resolver=policy, registrations=registrations))
        browser = _CurrentEmptyBrowser(source=authority, service=catalogue, snapshots=descriptors,
            permitted=permitted, revision=document["policy_revision"], cursor_key=cursor_key)
        authority.require_current()
        return catalogue, browser
    except Exception:
        raise _configuration_error() from None
