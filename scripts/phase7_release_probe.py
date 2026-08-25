#!/usr/bin/env python3
"""Safety-bounded authenticated smoke and mixed-load probe for Phase 7.

The probe talks only to the public Next.js proxy. It never accepts an internal
JWT or application secret. Operators provide an exported browser Cookie header
through a private file outside the repository; the value is never printed or
written to the result artifact.

Dry-run is the default. Network traffic requires ``--execute`` and an exact
``--confirm-host`` value for non-local targets.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import stat
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any
from urllib.parse import urlparse

import httpx


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAX_CONCURRENCY = 5
MAX_DURATION_SECONDS = 300
MAX_READ_REQUESTS = 300
MAX_CHAT_CALLS = 18
MAX_COOKIE_BYTES = 8192
REQUEST_TIMEOUT_SECONDS = 130.0
CHAT_RATE_PER_MINUTE = 9.0
READ_ENDPOINTS = (
    "/api/backend/health",
    "/api/backend/stats",
    "/api/backend/models",
    "/api/backend/documents?limit=5",
)
CHAT_QUESTIONS = (
    "Summarize the April 2024 Onagawa Bay temperature and salinity profile. Cite the evidence.",
    "Compare CTD surface temperature with satellite SST reliability in Onagawa Bay. Cite the evidence.",
    "Which retrieved sources support the strongest seasonal CTD pattern? Cite the evidence.",
)


class ProbeSafetyError(ValueError):
    """Raised before traffic when a Phase 7 safety bound is violated."""


@dataclass(frozen=True)
class ProbeConfig:
    base_url: str
    host: str
    mode: str
    execute: bool
    concurrency: int
    duration_seconds: int
    read_requests: int
    chat_calls: int


@dataclass(frozen=True)
class RequestResult:
    kind: str
    endpoint: str
    status_code: int
    latency_ms: int
    ok: bool
    model: str | None = None
    citation_count: int | None = None
    valid_citations: int | None = None
    invalid_citations: int | None = None
    error: str | None = None


def _is_local_host(host: str) -> bool:
    return host in {"localhost", "127.0.0.1", "::1"}


def validate_config(args: argparse.Namespace) -> ProbeConfig:
    parsed = urlparse(args.base_url)
    if not parsed.hostname or parsed.username or parsed.password:
        raise ProbeSafetyError("base URL must contain a hostname and no credentials")
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ProbeSafetyError("base URL must be an origin without a path, query, or fragment")
    if parsed.scheme not in {"http", "https"}:
        raise ProbeSafetyError("base URL scheme must be http or https")
    if not _is_local_host(parsed.hostname) and parsed.scheme != "https":
        raise ProbeSafetyError("non-local probes require HTTPS")
    if not 1 <= args.concurrency <= MAX_CONCURRENCY:
        raise ProbeSafetyError(f"concurrency must be between 1 and {MAX_CONCURRENCY}")
    if not 1 <= args.duration_seconds <= MAX_DURATION_SECONDS:
        raise ProbeSafetyError(
            f"duration must be between 1 and {MAX_DURATION_SECONDS} seconds"
        )
    if not 1 <= args.read_requests <= MAX_READ_REQUESTS:
        raise ProbeSafetyError(
            f"read requests must be between 1 and {MAX_READ_REQUESTS}"
        )
    if not 0 <= args.chat_calls <= MAX_CHAT_CALLS:
        raise ProbeSafetyError(f"chat calls must be between 0 and {MAX_CHAT_CALLS}")
    if args.mode == "smoke" and args.chat_calls > 3:
        raise ProbeSafetyError("smoke mode permits at most three chat calls")
    if args.mode == "load" and args.chat_calls:
        rate = args.chat_calls * 60 / args.duration_seconds
        if rate > CHAT_RATE_PER_MINUTE:
            raise ProbeSafetyError(
                "chat schedule would exceed the nine-per-minute Phase 7 ceiling"
            )
    if args.execute and not _is_local_host(parsed.hostname):
        if args.confirm_host != parsed.hostname:
            raise ProbeSafetyError(
                "--confirm-host must exactly match the production hostname"
            )
    return ProbeConfig(
        base_url=f"{parsed.scheme}://{parsed.netloc}",
        host=parsed.hostname,
        mode=args.mode,
        execute=args.execute,
        concurrency=args.concurrency,
        duration_seconds=args.duration_seconds,
        read_requests=args.read_requests,
        chat_calls=args.chat_calls,
    )


def read_private_cookie(path: Path | None) -> str:
    if path is None:
        raise ProbeSafetyError("--cookie-file is required with --execute")
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError:
        pass
    else:
        raise ProbeSafetyError("cookie file must be outside the repository")
    if not resolved.is_file():
        raise ProbeSafetyError("cookie file does not exist")
    if os.name == "posix" and stat.S_IMODE(resolved.stat().st_mode) & 0o077:
        raise ProbeSafetyError("cookie file permissions must be 0600 or stricter")
    if resolved.stat().st_size > MAX_COOKIE_BYTES:
        raise ProbeSafetyError("cookie file exceeds the 8192-byte limit")
    value = resolved.read_text(encoding="utf-8").strip()
    if value.lower().startswith("cookie:"):
        value = value.split(":", 1)[1].strip()
    if not value or "\n" in value or "\r" in value:
        raise ProbeSafetyError("cookie file must contain one Cookie header value")
    return value


def _quantile(values: list[int], quantile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(len(ordered) * quantile) - 1)
    return ordered[index]


def _audit_counts(payload: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    audit = payload.get("answer_audit")
    if not isinstance(audit, dict):
        return None, None, None
    citations = audit.get("citations")
    if not isinstance(citations, list):
        return None, None, None
    valid = sum(1 for row in citations if isinstance(row, dict) and row.get("valid") is True)
    invalid = sum(1 for row in citations if isinstance(row, dict) and row.get("valid") is False)
    return len(citations), valid, invalid


async def _request(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    *,
    kind: str,
    endpoint: str,
    payload: dict[str, Any] | None = None,
) -> RequestResult:
    started = time.perf_counter()
    try:
        async with semaphore:
            if payload is None:
                response = await client.get(endpoint)
            else:
                response = await client.post(endpoint, json=payload)
        latency_ms = round((time.perf_counter() - started) * 1000)
        model = None
        citation_count = valid_citations = invalid_citations = None
        if kind == "chat" and response.status_code == 200:
            body = response.json()
            model = str(body.get("model") or "") or None
            citation_count, valid_citations, invalid_citations = _audit_counts(body)
        return RequestResult(
            kind=kind,
            endpoint=endpoint.split("?", 1)[0],
            status_code=response.status_code,
            latency_ms=latency_ms,
            ok=response.status_code == 200 and invalid_citations in {None, 0},
            model=model,
            citation_count=citation_count,
            valid_citations=valid_citations,
            invalid_citations=invalid_citations,
            error=None if response.status_code == 200 else f"HTTP {response.status_code}",
        )
    except Exception as exc:
        return RequestResult(
            kind=kind,
            endpoint=endpoint.split("?", 1)[0],
            status_code=0,
            latency_ms=round((time.perf_counter() - started) * 1000),
            ok=False,
            error=type(exc).__name__,
        )


async def _scheduled_request(delay: float, *args: Any, **kwargs: Any) -> RequestResult:
    if delay > 0:
        await asyncio.sleep(delay)
    return await _request(*args, **kwargs)


async def execute_probe(config: ProbeConfig, cookie: str) -> list[RequestResult]:
    semaphore = asyncio.Semaphore(config.concurrency)
    headers = {
        "Accept": "application/json",
        "Cookie": cookie,
        "Origin": config.base_url,
        "Referer": f"{config.base_url}/",
        "User-Agent": "ocean-platform-release-probe/1",
    }
    timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(
        base_url=config.base_url,
        headers=headers,
        follow_redirects=False,
        timeout=timeout,
    ) as client:
        tasks: list[asyncio.Task[RequestResult]] = []
        if config.mode == "smoke":
            for index in range(config.read_requests):
                endpoint = READ_ENDPOINTS[index % len(READ_ENDPOINTS)]
                tasks.append(
                    asyncio.create_task(
                        _scheduled_request(
                            0,
                            client,
                            semaphore,
                            kind="read",
                            endpoint=endpoint,
                        )
                    )
                )
            for index in range(config.chat_calls):
                tasks.append(
                    asyncio.create_task(
                        _scheduled_request(
                            0,
                            client,
                            semaphore,
                            kind="chat",
                            endpoint="/api/backend/chat",
                            payload={"query": CHAT_QUESTIONS[index % len(CHAT_QUESTIONS)]},
                        )
                    )
                )
        else:
            for index in range(config.read_requests):
                delay = index * config.duration_seconds / config.read_requests
                endpoint = READ_ENDPOINTS[index % len(READ_ENDPOINTS)]
                tasks.append(
                    asyncio.create_task(
                        _scheduled_request(
                            delay,
                            client,
                            semaphore,
                            kind="read",
                            endpoint=endpoint,
                        )
                    )
                )
            for index in range(config.chat_calls):
                delay = (index + 0.5) * config.duration_seconds / config.chat_calls
                tasks.append(
                    asyncio.create_task(
                        _scheduled_request(
                            delay,
                            client,
                            semaphore,
                            kind="chat",
                            endpoint="/api/backend/chat",
                            payload={"query": CHAT_QUESTIONS[index % len(CHAT_QUESTIONS)]},
                        )
                    )
                )
        return list(await asyncio.gather(*tasks))


def summarize(config: ProbeConfig, results: list[RequestResult]) -> dict[str, Any]:
    read_latencies = [row.latency_ms for row in results if row.kind == "read"]
    chat_latencies = [row.latency_ms for row in results if row.kind == "chat"]
    status_counts: dict[str, int] = {}
    for row in results:
        key = str(row.status_code)
        status_counts[key] = status_counts.get(key, 0) + 1
    return {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "config": asdict(config),
        "limits": {
            "max_concurrency": MAX_CONCURRENCY,
            "max_duration_seconds": MAX_DURATION_SECONDS,
            "max_read_requests": MAX_READ_REQUESTS,
            "max_chat_calls": MAX_CHAT_CALLS,
            "chat_rate_per_minute": CHAT_RATE_PER_MINUTE,
        },
        "summary": {
            "requests": len(results),
            "passed": sum(1 for row in results if row.ok),
            "failed": sum(1 for row in results if not row.ok),
            "status_counts": status_counts,
            "read_latency_ms": {
                "mean": round(mean(read_latencies), 1) if read_latencies else None,
                "p95": _quantile(read_latencies, 0.95),
                "max": max(read_latencies) if read_latencies else None,
            },
            "chat_latency_ms": {
                "mean": round(mean(chat_latencies), 1) if chat_latencies else None,
                "p95": _quantile(chat_latencies, 0.95),
                "max": max(chat_latencies) if chat_latencies else None,
            },
        },
        "requests": [asdict(row) for row in results],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--mode", choices=("smoke", "load"), default="smoke")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-host")
    parser.add_argument("--cookie-file", type=Path)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--duration-seconds", type=int, default=180)
    parser.add_argument("--read-requests", type=int, default=12)
    parser.add_argument("--chat-calls", type=int, default=0)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    try:
        config = validate_config(args)
        if config.execute:
            cookie = read_private_cookie(args.cookie_file)
            results = asyncio.run(execute_probe(config, cookie))
        else:
            results = []
        report = summarize(config, results)
    except ProbeSafetyError as exc:
        parser.error(str(exc))

    output = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{output}\n", encoding="utf-8")
    print(output)
    if not config.execute:
        print("Dry-run only. Add --execute with a private cookie file to send traffic.", file=sys.stderr)
        return 0
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
