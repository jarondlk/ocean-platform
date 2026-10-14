"""Read-only F03 smoke probes using synthetic identity and limiter delays."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from api import auth
from starlette.requests import Request
from starlette.responses import Response


async def probe(operation):
    loop_thread = threading.get_ident()
    observed = {}
    downstream_calls = []

    async def heartbeat():
        started = time.perf_counter()
        await asyncio.sleep(0.01)
        observed['heartbeat_actual_ms'] = round((time.perf_counter() - started) * 1000, 2)

    def delayed(*arguments, **keywords):
        observed['blocking_operation_on_event_loop_thread'] = threading.get_ident() == loop_thread
        time.sleep(0.15)
        return auth._disabled_mode_user() if operation == 'authentication' else None

    async def downstream(request):
        downstream_calls.append(str(request.state.current_user.id))
        return Response('synthetic ok')

    request = Request({'type': 'http', 'method': 'POST', 'path': '/chat', 'headers': []})
    task = asyncio.create_task(heartbeat())
    await asyncio.sleep(0)
    with patch.object(auth, 'authenticate_request', delayed if operation == 'authentication'
                      else lambda request: auth._disabled_mode_user()), \
            patch.object(auth.config, 'production_like_environment', return_value=operation == 'limiter'), \
            patch.object(auth.rate_limiter, 'retry_after', delayed):
        response = await auth.authorization_middleware(request, downstream)
    await task
    observed.update(operation=operation, synthetic_delay_ms=150, heartbeat_requested_ms=10,
                    response_status=response.status_code, downstream_calls=len(downstream_calls),
                    scope='Synthetic smoke measurement; no production latency or throughput claim')
    return observed


async def main():
    # Thread identity establishes the boundary; timings are observations only.
    return [await probe('authentication'), await probe('limiter')]


if __name__ == '__main__':
    results = asyncio.run(main())
    (Path(__file__).resolve().parent / 'authentication-probes.json').write_text(
        json.dumps(results, indent=2) + '\n'
    )
    print(json.dumps(results, indent=2))
