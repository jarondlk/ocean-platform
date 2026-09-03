"""Bounded, credential-safe acquisition for ANEMONE MiFish evidence."""
from __future__ import annotations

import base64
import csv
import getpass
import hashlib
from http.client import IncompleteRead
import json
import lzma
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import config


USER_AGENT = "OCEAN-Platform-ANEMONE-sync/0.4"
SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
SEQUENCE_PATTERN = re.compile(r"^[ACGTNacgtn]+$")
RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}


class AnemoneError(RuntimeError):
    """A sanitized acquisition or validation failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, repr=False)
class AnemoneCredentials:
    """Basic-auth values that must never be serialized or logged."""

    username: str
    password: str

    def __repr__(self) -> str:
        return "AnemoneCredentials(username=<redacted>, password=<redacted>)"

    def authorization_header(self) -> str:
        token = base64.b64encode(
            f"{self.username}:{self.password}".encode("utf-8")
        ).decode("ascii")
        return f"Basic {token}"


@dataclass(frozen=True)
class AnemoneScope:
    url: str
    level: str
    segments: tuple[str, ...]


@dataclass
class AnemoneIssue:
    severity: str
    code: str
    message: str
    relative_path: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "relative_path": self.relative_path,
        }


@dataclass
class AnemoneRemoteFile:
    relative_path: str
    source_url: str
    sample_name: str
    role: str
    selection_status: str
    table_contract: Optional[str]
    size_bytes: Optional[int] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    sha256: Optional[str] = None
    validation_status: str = "not_downloaded"
    row_count: Optional[int] = None
    downloaded_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "source_url": self.source_url,
            "sample_name": self.sample_name,
            "role": self.role,
            "selection_status": self.selection_status,
            "size_bytes": self.size_bytes,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "sha256": self.sha256,
            "validation_status": self.validation_status,
            "row_count": self.row_count,
            "downloaded_at": self.downloaded_at,
        }


@dataclass
class AnemoneInventory:
    scope: AnemoneScope
    contract_version: int
    contract_sha256: str
    files: list[AnemoneRemoteFile]
    issues: list[AnemoneIssue] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def selected_files(self) -> list[AnemoneRemoteFile]:
        return [f for f in self.files if f.selection_status == "selected"]


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, Optional[str]]],
    ) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.links.append(value)


class _BoundedRedirectHandler(HTTPRedirectHandler):
    """Reject a redirect before urllib can forward the auth header to it."""

    def __init__(self, validate_url: Callable[[str], None]) -> None:
        super().__init__()
        self._validate_url = validate_url

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Optional[Request]:
        self._validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _read_secret_file(path: Path, label: str) -> str:
    resolved = path.expanduser().resolve()
    project_root = config.PROJECT_ROOT.resolve()
    if resolved == project_root or project_root in resolved.parents:
        raise AnemoneError(
            "credential_path_unsafe",
            f"{label} credential file must be outside the repository.",
        )
    try:
        value = resolved.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise AnemoneError(
            "credential_file_unreadable",
            f"{label} credential file is unreadable.",
        ) from exc
    if not value:
        raise AnemoneError(
            "credential_file_empty",
            f"{label} credential file is empty.",
        )
    return value


def resolve_credentials(
    *,
    username_file: Optional[Path] = None,
    password_file: Optional[Path] = None,
    environ: Optional[Mapping[str, str]] = None,
    prompt: bool = True,
    input_fn: Callable[[str], str] = input,
    password_fn: Callable[[str], str] = getpass.getpass,
) -> AnemoneCredentials:
    """Resolve credentials without accepting or emitting them as CLI values."""
    env = os.environ if environ is None else environ
    username = (
        _read_secret_file(username_file, "Username")
        if username_file
        else str(env.get("ANEMONE_DOWNLOAD_USERNAME", "")).strip()
    )
    password = (
        _read_secret_file(password_file, "Password")
        if password_file
        else str(env.get("ANEMONE_DOWNLOAD_PASSWORD", "")).strip()
    )
    if prompt and sys.stdin.isatty():
        if not username:
            username = input_fn("ANEMONE download username: ").strip()
        if not password:
            password = password_fn("ANEMONE download password: ").strip()
    if not username or not password:
        raise AnemoneError(
            "credentials_missing",
            "ANEMONE download credentials are required.",
        )
    return AnemoneCredentials(username=username, password=password)


def load_contract(path: Path = config.ANEMONE_CONTRACT_PATH) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnemoneError(
            "contract_unreadable",
            "ANEMONE source contract is unreadable.",
        ) from exc
    if contract.get("schema_version") != 1:
        raise AnemoneError(
            "contract_version_unsupported",
            "ANEMONE source contract version is unsupported.",
        )
    return contract


def load_contract_by_hash(contract_sha256: str) -> dict[str, Any]:
    """Resolve only repository-approved contracts, never paths from a manifest."""
    candidates = (
        config.ANEMONE_CONTRACT_PATH,
        config.PROJECT_ROOT / "data_contracts" / "history" / "anemone_mifish_v1.json",
    )
    for path in candidates:
        contract = load_contract(path)
        if _contract_hash(contract) == contract_sha256:
            return contract
    raise AnemoneError(
        "snapshot_contract_unknown",
        "ANEMONE snapshot does not match an approved source contract.",
    )


def validate_scope_url(
    url: str,
    *,
    base_url: str = config.ANEMONE_BASE_URL,
    allow_insecure_http: bool = False,
) -> AnemoneScope:
    """Accept only exact ANEMONE sample or sequencing-run directory URLs."""
    parsed = urlsplit(url)
    base = urlsplit(base_url)
    allowed_schemes = {"https"}
    if allow_insecure_http:
        allowed_schemes.add("http")
    if parsed.scheme not in allowed_schemes or base.scheme not in allowed_schemes:
        raise AnemoneError("scope_scheme_invalid", "ANEMONE scope must use HTTPS.")
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or base.username
        or base.password
        or base.query
        or base.fragment
    ):
        raise AnemoneError(
            "scope_components_invalid",
            "ANEMONE scope cannot contain credentials, query, or fragment.",
        )
    if (parsed.scheme, parsed.hostname, parsed.port) != (
        base.scheme,
        base.hostname,
        base.port,
    ):
        raise AnemoneError(
            "scope_origin_invalid",
            "ANEMONE scope must remain on the approved origin.",
        )
    base_path = base.path if base.path.endswith("/") else f"{base.path}/"
    if not parsed.path.startswith(base_path) or not parsed.path.endswith("/"):
        raise AnemoneError(
            "scope_path_invalid",
            "ANEMONE scope must be a child directory of the approved prefix.",
        )
    tail = parsed.path[len(base_path) : -1]
    segments = tuple(part for part in tail.split("/") if part)
    if len(segments) not in {2, 3}:
        raise AnemoneError(
            "scope_level_invalid",
            "ANEMONE scope must identify one sequencing run or sample.",
        )
    if any(not SAFE_SEGMENT.fullmatch(part) for part in segments):
        raise AnemoneError(
            "scope_identifier_invalid",
            "ANEMONE scope contains an unsupported identifier.",
        )
    normalized_path = base_path + "/".join(segments) + "/"
    normalized = urlunsplit((parsed.scheme, parsed.netloc, normalized_path, "", ""))
    return AnemoneScope(
        url=normalized,
        level="sample" if len(segments) == 3 else "run",
        segments=segments,
    )


class AnemoneHttpClient:
    """Small retrying HTTP client with redirect and secret boundaries."""

    def __init__(
        self,
        credentials: AnemoneCredentials,
        *,
        base_url: str = config.ANEMONE_BASE_URL,
        allow_insecure_http: bool = False,
        timeout: float = 30.0,
        max_attempts: int = 3,
        retry_initial_seconds: float = 0.25,
        opener: Any = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._authorization = credentials.authorization_header()
        self.base_url = base_url
        self.allow_insecure_http = allow_insecure_http
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.retry_initial_seconds = retry_initial_seconds
        self.opener = opener or build_opener(_BoundedRedirectHandler(self._validate_final_url))
        self.sleep_fn = sleep_fn

    def open(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Optional[dict[str, str]] = None,
    ) -> Any:
        request_headers = {
            "Authorization": self._authorization,
            "User-Agent": USER_AGENT,
            **(headers or {}),
        }
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.opener.open(
                    Request(url, method=method, headers=request_headers),
                    timeout=self.timeout,
                )
                self._validate_final_url(response.geturl())
                return response
            except HTTPError as exc:
                if exc.code in {401, 403}:
                    raise AnemoneError(
                        "authentication_failed",
                        f"ANEMONE authentication failed with HTTP {exc.code}.",
                    ) from exc
                if exc.code not in RETRYABLE_HTTP_STATUS or attempt == self.max_attempts:
                    raise AnemoneError(
                        "http_request_failed",
                        f"ANEMONE request failed with HTTP {exc.code}.",
                    ) from exc
            except URLError as exc:
                if attempt == self.max_attempts:
                    raise AnemoneError(
                        "network_request_failed",
                        "ANEMONE request failed due to a network error.",
                    ) from exc
            self.sleep_fn(self.retry_initial_seconds * (2 ** (attempt - 1)))
        raise AssertionError("unreachable")

    def _validate_final_url(self, url: str) -> None:
        parsed = urlsplit(url)
        base = urlsplit(self.base_url)
        allowed_schemes = {"https"}
        if self.allow_insecure_http:
            allowed_schemes.add("http")
        base_path = base.path if base.path.endswith("/") else f"{base.path}/"
        if (
            parsed.scheme not in allowed_schemes
            or (parsed.scheme, parsed.hostname, parsed.port)
            != (base.scheme, base.hostname, base.port)
            or not parsed.path.startswith(base_path)
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise AnemoneError(
                "redirect_outside_scope",
                "ANEMONE redirected outside the approved source boundary.",
            )

    def read_directory(self, url: str, maximum_bytes: int) -> str:
        response = self.open(url)
        try:
            body = response.read(maximum_bytes + 1)
        finally:
            response.close()
        if len(body) > maximum_bytes:
            raise AnemoneError(
                "directory_listing_too_large",
                "ANEMONE directory listing exceeds the configured limit.",
            )
        return body.decode("utf-8", "replace")

    def metadata(self, url: str) -> dict[str, Any]:
        try:
            response = self.open(url, method="HEAD")
        except AnemoneError as exc:
            if exc.code != "http_request_failed":
                raise
            response = self.open(url, headers={"Range": "bytes=0-0"})
        try:
            length = response.headers.get("Content-Length")
            content_range = response.headers.get("Content-Range", "")
            total_match = re.fullmatch(r"bytes \d+-\d+/(\d+)", content_range)
            size_bytes = (
                int(total_match.group(1))
                if total_match
                else int(length)
                if length and length.isdigit()
                else None
            )
            return {
                "size_bytes": size_bytes,
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
            }
        finally:
            response.close()


def _extract_links(html: str) -> list[str]:
    parser = _LinkParser()
    parser.feed(html)
    return sorted(set(parser.links))


def _direct_child_links(
    directory_url: str,
    html: str,
) -> tuple[list[str], list[str]]:
    """Return direct child directories and files without allowing traversal."""
    directory = urlsplit(directory_url)
    directories: list[str] = []
    files: list[str] = []
    for href in _extract_links(html):
        if href == "../" or not href:
            continue
        candidate_url = urljoin(directory_url, href)
        candidate = urlsplit(candidate_url)
        if (
            candidate.scheme != directory.scheme
            or candidate.netloc != directory.netloc
            or candidate.query
            or candidate.fragment
        ):
            files.append(candidate_url)
            continue
        parent = directory.path if directory.path.endswith("/") else directory.path + "/"
        if not candidate.path.startswith(parent):
            files.append(candidate_url)
            continue
        tail = candidate.path[len(parent) :]
        if not tail or "/" in tail.rstrip("/"):
            files.append(candidate_url)
            continue
        if candidate.path.endswith("/"):
            directories.append(candidate_url)
        else:
            files.append(candidate_url)
    return sorted(set(directories)), sorted(set(files))


def _role_for_file(name: str, contract: dict[str, Any]) -> dict[str, Any]:
    for item in contract.get("file_roles", []):
        if re.fullmatch(str(item["pattern"]), name):
            return dict(item)
    return {"role": "unknown", "selection": "unknown"}


def _relative_remote_path(scope: AnemoneScope, sample_url: str, file_url: str) -> str:
    sample_name = urlsplit(sample_url).path.rstrip("/").rsplit("/", 1)[-1]
    file_name = urlsplit(file_url).path.rsplit("/", 1)[-1]
    if scope.level == "sample":
        return file_name
    return f"{sample_name}/{file_name}"


def _contract_hash(contract: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _source_collection_hash(inventory: AnemoneInventory) -> str:
    payload = {
        "contract_sha256": inventory.contract_sha256,
        "files": [
            {
                "relative_path": item.relative_path,
                "source_url": item.source_url,
                "role": item.role,
                "selection_status": item.selection_status,
                "size_bytes": item.size_bytes,
                "etag": item.etag,
                "last_modified": item.last_modified,
            }
            for item in sorted(inventory.files, key=lambda value: value.relative_path)
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _completed_collection_hash(inventory: AnemoneInventory) -> str:
    payload = {
        "contract_sha256": inventory.contract_sha256,
        "files": [
            {
                **item.to_dict(),
                "downloaded_at": None,
            }
            for item in sorted(
                inventory.files,
                key=lambda value: value.relative_path,
            )
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def inventory_anemone(
    scope_url: str,
    *,
    credentials: AnemoneCredentials,
    contract: Optional[dict[str, Any]] = None,
    base_url: Optional[str] = None,
    max_files: Optional[int] = None,
    max_bytes: Optional[int] = None,
    allow_insecure_http: bool = False,
    client: Optional[AnemoneHttpClient] = None,
    generated_at: Optional[str] = None,
) -> AnemoneInventory:
    contract = contract or load_contract()
    source_base = base_url or str(contract.get("base_url") or config.ANEMONE_BASE_URL)
    scope = validate_scope_url(
        scope_url,
        base_url=source_base,
        allow_insecure_http=allow_insecure_http,
    )
    limits = contract.get("limits", {})
    maximum_files = max_files or int(limits.get("maximum_files") or config.ANEMONE_MAX_FILES)
    maximum_bytes = max_bytes or int(
        limits.get("maximum_download_bytes") or config.ANEMONE_MAX_BYTES
    )
    directory_limit = int(limits.get("maximum_directory_bytes") or 2_000_000)
    http = client or AnemoneHttpClient(
        credentials,
        base_url=source_base,
        allow_insecure_http=allow_insecure_http,
    )
    issues: list[AnemoneIssue] = []
    sample_urls: list[str]
    if scope.level == "sample":
        sample_urls = [scope.url]
    else:
        run_html = http.read_directory(scope.url, directory_limit)
        child_dirs, run_files = _direct_child_links(scope.url, run_html)
        sample_urls = []
        for child in child_dirs:
            try:
                sample_scope = validate_scope_url(
                    child,
                    base_url=source_base,
                    allow_insecure_http=allow_insecure_http,
                )
            except AnemoneError:
                issues.append(
                    AnemoneIssue(
                        "error",
                        "unexpected_run_child",
                        "Sequencing-run listing contains an unsupported child.",
                    )
                )
                continue
            if sample_scope.level != "sample" or sample_scope.segments[:2] != scope.segments:
                issues.append(
                    AnemoneIssue(
                        "error",
                        "unexpected_run_child",
                        "Sequencing-run listing contains an out-of-scope sample.",
                    )
                )
                continue
            sample_urls.append(sample_scope.url)
        if run_files:
            issues.append(
                AnemoneIssue(
                    "error",
                    "unexpected_run_file",
                    "Sequencing-run directory contains an unexpected file or link.",
                )
            )
        if not sample_urls:
            issues.append(
                AnemoneIssue(
                    "error",
                    "run_has_no_samples",
                    "Sequencing-run directory contains no valid samples.",
                )
            )
        elif len(sample_urls) > maximum_files:
            issues.append(
                AnemoneIssue(
                    "error",
                    "file_limit_exceeded",
                    "Sequencing-run sample count exceeds the configured file limit.",
                )
            )
            sample_urls = []

    files: list[AnemoneRemoteFile] = []
    required_roles = set(contract.get("required_selected_roles") or [])
    for sample_url in sorted(set(sample_urls)):
        sample_name = urlsplit(sample_url).path.rstrip("/").rsplit("/", 1)[-1]
        html = http.read_directory(sample_url, directory_limit)
        subdirs, child_files = _direct_child_links(sample_url, html)
        if subdirs:
            issues.append(
                AnemoneIssue(
                    "error",
                    "unexpected_sample_directory",
                    "Sample directory contains an unexpected child directory.",
                    sample_name,
                )
            )
        if len(files) + len(child_files) > maximum_files:
            issues.append(
                AnemoneIssue(
                    "error",
                    "file_limit_exceeded",
                    "Discovered source links exceed the configured file limit.",
                    sample_name,
                )
            )
            break
        observed_roles: set[str] = set()
        for file_url in child_files:
            parsed_file = urlsplit(file_url)
            parsed_sample = urlsplit(sample_url)
            if (
                parsed_file.scheme != parsed_sample.scheme
                or parsed_file.netloc != parsed_sample.netloc
                or not parsed_file.path.startswith(parsed_sample.path)
                or parsed_file.query
                or parsed_file.fragment
            ):
                issues.append(
                    AnemoneIssue(
                        "error",
                        "file_outside_scope",
                        "Sample listing contains an out-of-scope file link.",
                        sample_name,
                    )
                )
                continue
            name = parsed_file.path.rsplit("/", 1)[-1]
            if not SAFE_SEGMENT.fullmatch(name):
                issues.append(
                    AnemoneIssue(
                        "error",
                        "file_name_invalid",
                        "Sample listing contains an unsupported file name.",
                        sample_name,
                    )
                )
                continue
            role_spec = _role_for_file(name, contract)
            metadata = http.metadata(file_url)
            relative = _relative_remote_path(scope, sample_url, file_url)
            role = str(role_spec["role"])
            selection = str(role_spec["selection"])
            observed_roles.add(role)
            files.append(
                AnemoneRemoteFile(
                    relative_path=relative,
                    source_url=file_url,
                    sample_name=sample_name,
                    role=role,
                    selection_status=selection,
                    table_contract=role_spec.get("table_contract"),
                    **metadata,
                )
            )
            if selection == "unknown":
                issues.append(
                    AnemoneIssue(
                        "error",
                        "unknown_source_file",
                        "Sample contains a file not covered by the source contract.",
                        relative,
                    )
                )
        missing_roles = sorted(required_roles - observed_roles)
        if missing_roles:
            issues.append(
                AnemoneIssue(
                    "error",
                    "required_file_missing",
                    "Sample is missing required interpreted file roles: "
                    + ", ".join(missing_roles),
                    sample_name,
                )
            )

    files.sort(key=lambda item: item.relative_path)
    if len(files) > maximum_files:
        issues.append(
            AnemoneIssue(
                "error",
                "file_limit_exceeded",
                f"Inventory contains {len(files)} files; limit is {maximum_files}.",
            )
        )
    known_selected_bytes = sum(
        item.size_bytes or 0 for item in files if item.selection_status == "selected"
    )
    if known_selected_bytes > maximum_bytes:
        issues.append(
            AnemoneIssue(
                "error",
                "byte_limit_exceeded",
                "Known selected-file bytes exceed the configured download limit.",
            )
        )
    duplicate_paths = sorted(
        path
        for path in {item.relative_path for item in files}
        if sum(item.relative_path == path for item in files) > 1
    )
    if duplicate_paths:
        issues.append(
            AnemoneIssue(
                "error",
                "duplicate_relative_path",
                "Inventory contains duplicate normalized relative paths.",
            )
        )
    return AnemoneInventory(
        scope=scope,
        contract_version=int(contract.get("contract_version", contract["schema_version"])),
        contract_sha256=_contract_hash(contract),
        files=files,
        issues=issues,
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
    )


def inventory_manifest(
    inventory: AnemoneInventory,
    *,
    max_files: int,
    max_bytes: int,
    mode: str = "inventory",
) -> dict[str, Any]:
    source_hash = _source_collection_hash(inventory)
    total_bytes = sum(item.size_bytes or 0 for item in inventory.selected_files)
    return {
        "schema_version": 1,
        "source_provider": "anemone",
        "source_family": "edna_metabarcoding",
        "scope_url": inventory.scope.url,
        "scope_level": inventory.scope.level,
        "generated_at": inventory.generated_at,
        "mode": mode,
        "contract_version": inventory.contract_version,
        "contract_sha256": inventory.contract_sha256,
        "selection_policy": "interpreted_tsv_only",
        "limits": {"maximum_files": max_files, "maximum_bytes": max_bytes},
        "ok": inventory.ok,
        "file_count": len(inventory.files),
        "selected_file_count": len(inventory.selected_files),
        "total_bytes": total_bytes,
        "total_known_selected_bytes": total_bytes,
        "source_collection_sha256": source_hash,
        "collection_sha256": source_hash,
        "files": [item.to_dict() for item in inventory.files],
        "issues": [issue.to_dict() for issue in inventory.issues],
    }


def _safe_destination(root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise AnemoneError(
            "destination_path_invalid",
            "ANEMONE file has an unsafe destination path.",
        )
    destination = root.joinpath(*relative.parts)
    resolved_root = root.resolve()
    resolved_parent = destination.parent.resolve()
    if resolved_parent != resolved_root and resolved_root not in resolved_parent.parents:
        raise AnemoneError(
            "destination_path_invalid",
            "ANEMONE file escapes the staging directory.",
        )
    return destination


def _download_file(
    client: AnemoneHttpClient,
    item: AnemoneRemoteFile,
    destination: Path,
    *,
    remaining_bytes: int,
) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        existing_complete = destination.stat().st_size
        if existing_complete > remaining_bytes:
            raise AnemoneError(
                "byte_limit_exceeded",
                "ANEMONE download exceeds the configured byte limit.",
            )
        if not (item.etag or item.last_modified):
            destination.unlink()
        elif item.size_bytes is not None and existing_complete != item.size_bytes:
            destination.unlink()
        else:
            return existing_complete
    partial = destination.with_suffix(destination.suffix + ".part")
    existing = partial.stat().st_size if partial.exists() else 0
    headers: dict[str, str] = {}
    if existing:
        validator = item.etag or item.last_modified
        if not validator:
            partial.unlink()
            existing = 0
        else:
            headers["Range"] = f"bytes={existing}-"
            headers["If-Range"] = validator
    response = client.open(item.source_url, headers=headers)
    try:
        status = int(getattr(response, "status", response.getcode()))
        response_etag = response.headers.get("ETag")
        response_modified = response.headers.get("Last-Modified")
        if existing and status == 206:
            content_range = response.headers.get("Content-Range", "")
            if not content_range.startswith(f"bytes {existing}-"):
                raise AnemoneError(
                    "resume_range_invalid",
                    "ANEMONE resume response has an invalid byte range.",
                )
            if item.etag and response_etag != item.etag:
                raise AnemoneError(
                    "source_changed_during_resume",
                    "ANEMONE source changed while a partial transfer existed.",
                )
            if (
                not item.etag
                and item.last_modified
                and response_modified != item.last_modified
            ):
                raise AnemoneError(
                    "source_changed_during_resume",
                    "ANEMONE source changed while a partial transfer existed.",
                )
            mode = "ab"
        else:
            if existing and (
                (item.etag and response_etag and item.etag != response_etag)
                or (
                    item.last_modified
                    and response_modified
                    and item.last_modified != response_modified
                )
            ):
                raise AnemoneError(
                    "source_changed_during_resume",
                    "ANEMONE source changed while a partial transfer existed.",
                )
            mode = "wb"
            existing = 0
        written = existing
        with partial.open(mode) as handle:
            while True:
                try:
                    chunk = response.read(1024 * 1024)
                except IncompleteRead as exc:
                    chunk = exc.partial
                    if chunk:
                        written += len(chunk)
                        if written > remaining_bytes:
                            raise AnemoneError(
                                "byte_limit_exceeded",
                                "ANEMONE download exceeds the configured byte limit.",
                            ) from exc
                        handle.write(chunk)
                    raise AnemoneError(
                        "download_incomplete",
                        "ANEMONE transfer ended before the expected byte count.",
                    ) from exc
                if not chunk:
                    break
                written += len(chunk)
                if written > remaining_bytes:
                    raise AnemoneError(
                        "byte_limit_exceeded",
                        "ANEMONE download exceeds the configured byte limit.",
                    )
                handle.write(chunk)
    finally:
        response.close()
    if item.size_bytes is not None and written != item.size_bytes:
        raise AnemoneError(
            "download_size_mismatch",
            "ANEMONE download size does not match the inventory.",
        )
    partial.replace(destination)
    return written


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_xz_tsv(path: Path, maximum_bytes: int) -> tuple[list[str], list[list[str]]]:
    try:
        with lzma.open(path, "rb") as handle:
            payload = handle.read(maximum_bytes + 1)
    except (OSError, lzma.LZMAError) as exc:
        raise AnemoneError(
            "xz_validation_failed",
            "ANEMONE interpreted file is not a valid XZ stream.",
        ) from exc
    if len(payload) > maximum_bytes:
        raise AnemoneError(
            "tsv_uncompressed_limit_exceeded",
            "ANEMONE interpreted TSV exceeds the uncompressed-byte limit.",
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AnemoneError(
            "tsv_encoding_invalid",
            "ANEMONE interpreted TSV is not UTF-8.",
        ) from exc
    rows = list(csv.reader(text.splitlines(), delimiter="\t"))
    if not rows:
        raise AnemoneError("tsv_empty", "ANEMONE interpreted TSV is empty.")
    return rows[0], rows[1:]


def _nonnegative_number(value: str, *, integer: bool = False) -> bool:
    try:
        parsed = int(value) if integer else float(value)
    except (TypeError, ValueError):
        return False
    return parsed >= 0


def _validate_interpreted_file(
    path: Path,
    item: AnemoneRemoteFile,
    contract: dict[str, Any],
) -> tuple[int, set[str]]:
    maximum = int(
        contract.get("limits", {}).get("maximum_uncompressed_tsv_bytes")
        or 67_108_864
    )
    header, rows = _read_xz_tsv(path, maximum)
    table_name = item.table_contract or ""
    table = dict(contract.get("tables", {}).get(table_name) or {})
    expected = list(table.get("columns") or [])
    if header != expected:
        raise AnemoneError(
            "tsv_columns_invalid",
            f"ANEMONE {item.role} TSV columns do not match the contract.",
        )
    if len(rows) < int(table.get("minimum_rows") or 0):
        raise AnemoneError(
            "tsv_row_count_below_contract",
            f"ANEMONE {item.role} TSV has too few rows.",
        )
    width = len(header)
    if any(len(row) != width for row in rows):
        raise AnemoneError(
            "tsv_row_width_invalid",
            f"ANEMONE {item.role} TSV contains a malformed row.",
        )
    sample_names = {row[0].strip() for row in rows if row and row[0].strip()}
    if len(sample_names) != 1:
        raise AnemoneError(
            "tsv_sample_set_invalid",
            f"ANEMONE {item.role} TSV must contain exactly one sample name.",
        )
    index = {name: position for position, name in enumerate(header)}
    if table_name == "community":
        for row in rows:
            sequence = row[index["sequence"]].strip()
            if not sequence or not SEQUENCE_PATTERN.fullmatch(sequence):
                raise AnemoneError(
                    "community_sequence_invalid",
                    "ANEMONE community TSV contains an invalid sequence.",
                )
            if not _nonnegative_number(row[index["nreads"]], integer=True):
                raise AnemoneError(
                    "community_reads_invalid",
                    "ANEMONE community TSV contains an invalid read count.",
                )
            copies = row[index["ncopiesperml"]].strip()
            if copies.upper() not in {"", "NA", "N/A"} and not _nonnegative_number(copies):
                raise AnemoneError(
                    "community_copies_invalid",
                    "ANEMONE community TSV contains invalid copies/mL.",
                )
    elif table_name == "standard":
        for row in rows:
            if not SEQUENCE_PATTERN.fullmatch(row[index["sequence"]].strip()):
                raise AnemoneError(
                    "standard_sequence_invalid",
                    "ANEMONE internal-standard TSV contains an invalid sequence.",
                )
            if not _nonnegative_number(row[index["nreads"]], integer=True):
                raise AnemoneError(
                    "standard_reads_invalid",
                    "ANEMONE internal-standard TSV contains an invalid read count.",
                )
    elif table_name.startswith("key_value_"):
        keys = [row[index["key"]].strip() for row in rows]
        if any(not key for key in keys) or len(keys) != len(set(keys)):
            raise AnemoneError(
                "metadata_keys_invalid",
                f"ANEMONE {item.role} contains blank or duplicate metadata keys.",
            )
        missing = sorted(set(table.get("required_keys") or []) - set(keys))
        if missing:
            raise AnemoneError(
                "metadata_keys_missing",
                f"ANEMONE {item.role} is missing required metadata keys: "
                + ", ".join(missing),
            )
    return len(rows), sample_names


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _existing_snapshot(output_root: Path, source_hash: str) -> Optional[dict[str, Any]]:
    snapshots = output_root / "snapshots"
    if not snapshots.exists():
        return None
    for manifest_path in sorted(snapshots.glob("*/manifest.json")):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            payload.get("source_collection_sha256") == source_hash
            and payload.get("selection_policy") == "interpreted_tsv_only"
            and payload.get("status") == "complete"
        ):
            return payload
    return None


def sync_anemone(
    scope_url: str,
    *,
    credentials: AnemoneCredentials,
    execute: bool = False,
    output_root: Path = config.RAW_ANEMONE_DIR,
    contract: Optional[dict[str, Any]] = None,
    base_url: Optional[str] = None,
    max_files: Optional[int] = None,
    max_bytes: Optional[int] = None,
    allow_insecure_http: bool = False,
    client: Optional[AnemoneHttpClient] = None,
    generated_at: Optional[str] = None,
) -> dict[str, Any]:
    """Inventory or acquire one bounded ANEMONE sample/run snapshot."""
    source_contract = contract or load_contract()
    limits = source_contract.get("limits", {})
    maximum_files = max_files or int(
        limits.get("maximum_files") or config.ANEMONE_MAX_FILES
    )
    maximum_bytes = max_bytes or int(
        limits.get("maximum_download_bytes") or config.ANEMONE_MAX_BYTES
    )
    source_base = base_url or str(
        source_contract.get("base_url") or config.ANEMONE_BASE_URL
    )
    http = client or AnemoneHttpClient(
        credentials,
        base_url=source_base,
        allow_insecure_http=allow_insecure_http,
    )
    inventory = inventory_anemone(
        scope_url,
        credentials=credentials,
        contract=source_contract,
        base_url=source_base,
        max_files=maximum_files,
        max_bytes=maximum_bytes,
        allow_insecure_http=allow_insecure_http,
        client=http,
        generated_at=generated_at,
    )
    manifest = inventory_manifest(
        inventory,
        max_files=maximum_files,
        max_bytes=maximum_bytes,
    )
    source_hash = str(manifest["source_collection_sha256"])
    if not execute:
        inventory_path = output_root / "inventory" / f"{source_hash}.json"
        _write_json(inventory_path, manifest)
        manifest["manifest_path"] = str(inventory_path)
        return manifest
    if not inventory.ok:
        codes = ", ".join(issue.code for issue in inventory.issues if issue.severity == "error")
        raise AnemoneError(
            "inventory_blocked",
            f"ANEMONE inventory failed validation: {codes}.",
        )
    existing = _existing_snapshot(output_root, source_hash)
    if existing is not None:
        return {**existing, "reused_snapshot": True}

    staging_root = output_root / "staging" / source_hash
    staging_root.mkdir(parents=True, exist_ok=True)
    written_total = 0
    sample_names_by_directory: dict[str, set[str]] = {}
    try:
        for item in inventory.selected_files:
            destination = _safe_destination(staging_root, item.relative_path)
            size = _download_file(
                http,
                item,
                destination,
                remaining_bytes=maximum_bytes - written_total,
            )
            written_total += size
            item.size_bytes = size
            item.sha256 = _sha256_file(destination)
            row_count, sample_names = _validate_interpreted_file(
                destination,
                item,
                source_contract,
            )
            directory = str(PurePosixPath(item.relative_path).parent)
            if directory == ".":
                directory = item.sample_name
            sample_names_by_directory.setdefault(directory, set()).update(sample_names)
            if sample_names != {item.sample_name}:
                raise AnemoneError(
                    "sample_name_mismatch",
                    "ANEMONE interpreted TSV sample name does not match its directory.",
                )
            item.validation_status = "valid"
            item.row_count = row_count
            item.downloaded_at = datetime.now(timezone.utc).isoformat()
        if any(len(names) != 1 for names in sample_names_by_directory.values()):
            raise AnemoneError(
                "sample_set_mismatch",
                "ANEMONE interpreted files disagree on the sample identifier.",
            )
        manifest = inventory_manifest(
            inventory,
            max_files=maximum_files,
            max_bytes=maximum_bytes,
            mode="execute",
        )
        manifest["status"] = "complete"
        manifest["downloaded_bytes"] = written_total
        manifest["collection_sha256"] = _completed_collection_hash(inventory)
        snapshot_id = str(manifest["collection_sha256"])
        final_root = output_root / "snapshots" / snapshot_id
        manifest["snapshot_id"] = snapshot_id
        manifest["snapshot_path"] = str(final_root)
        manifest["reused_snapshot"] = False
        _write_json(staging_root / "manifest.json", manifest)
        final_root.parent.mkdir(parents=True, exist_ok=True)
        if final_root.exists():
            existing_manifest = final_root / "manifest.json"
            if not existing_manifest.exists():
                raise AnemoneError(
                    "snapshot_collision",
                    "ANEMONE snapshot destination already exists without a manifest.",
                )
            shutil.rmtree(staging_root)
            return {
                **json.loads(existing_manifest.read_text(encoding="utf-8")),
                "reused_snapshot": True,
            }
        staging_root.replace(final_root)
        return manifest
    except Exception:
        # Keep the hash-addressed staging directory so the next identical run
        # can resume partial files. It is never treated as a complete snapshot.
        raise


__all__ = [
    "AnemoneCredentials",
    "AnemoneError",
    "AnemoneHttpClient",
    "AnemoneInventory",
    "AnemoneRemoteFile",
    "AnemoneScope",
    "inventory_anemone",
    "inventory_manifest",
    "load_contract",
    "resolve_credentials",
    "sync_anemone",
    "validate_scope_url",
]
