"""Explicit empty production catalogue authority for the independent beta.

This binds a genuine, configured zero-snapshot inventory. It does not discover
files, create a snapshot store, load fixtures, or approve/import scientific data.
Nonempty registries need a separate sealed-registration/current-policy binding;
this format deliberately refuses them rather than inventing that authority.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from pydantic import TypeAdapter

from orchestration.catalogue_browser import CatalogueBrowser
from orchestration.catalogue_service import (
    CatalogueService, CatalogueServiceError, catalogue_access_binding,
)
from schema.context_catalogue import Identifier

PROJECT = "ocean-v1-beta-20261101"
VERSION = "ocean-v1-empty-catalogue-v1"
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
        self._source.require_current()
        response = super().discover(payload, user)
        self._source.require_current()
        return response


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
