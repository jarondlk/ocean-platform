"""Read-only original/event-driven cancellation coordination comparison.

The alternative exists only in memory; repository app/test sources stay frozen.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT))

from coverage import Coverage  # noqa: E402
import pytest  # noqa: E402
from tests import test_catalogue_browser_api as original  # noqa: E402

PATHS = ['tests/test_catalogue_browser_api.py', 'api/catalogue_browser_routes.py',
         'orchestration/catalogue_browser.py', 'orchestration/catalogue_service.py']


def hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in PATHS}


def functions():
    source = inspect.getsource(original.test_policy_and_complete_response_stay_in_worker_with_cancellation_cleanup)
    source = source[source.index('def test_'):]
    alternate = source.replace('entered, release, closed = threading.Event(), threading.Event(), threading.Event()',
        'entered, release, closed = threading.Event(), threading.Event(), threading.Event()\n    encoded = threading.Event()')
    alternate = alternate.replace('super().__init__(*args, **kwargs)', 'super().__init__(*args, **kwargs)\n            encoded.set()')
    alternate = alternate.replace('while not entered.is_set():\n                    await anyio.sleep(0)',
        'assert await anyio.to_thread.run_sync(entered.wait, 5)')
    alternate = alternate.replace('while not closed.is_set() or not any(stage == "response" for stage, _ in stages):\n                await anyio.sleep(0)',
        'assert await anyio.to_thread.run_sync(encoded.wait, 5)\n            assert closed.is_set()')
    if alternate == source or 'while not' in alternate:
        raise AssertionError('Candidate was not an exact bounded wait replacement')
    outputs = {}
    for name, text in [('original', source), ('event', alternate)]:
        namespace = dict(original.__dict__)
        exec(compile(text, f'<read-only-{name}-coordination>', 'exec'), namespace)
        outputs[name] = namespace['test_policy_and_complete_response_stay_in_worker_with_cancellation_cleanup']
    return outputs, source, alternate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--iterations', type=int, default=2)
    parser.add_argument('--switch-interval', type=float, default=sys.getswitchinterval())
    parser.add_argument('--coverage', action='store_true')
    args = parser.parse_args()
    output = ROOT / args.output
    if output.exists():
        raise FileExistsError(output)
    before, results = hashes(), []
    funcs, source, alternate = functions()
    switch_before = sys.getswitchinterval()
    sys.setswitchinterval(args.switch_interval)
    cov = Coverage(data_file=None, source=['api', 'config', 'db', 'preprocessing', 'ingestion', 'orchestration', 'schema', 'evaluation'],
                   concurrency=['thread']) if args.coverage else None
    if cov:
        cov.start()
    try:
        for iteration in range(args.iterations):
            for cancel in (None, 'anyio', 'native'):
                for mode in ('original', 'event'):
                    with tempfile.TemporaryDirectory(prefix='c22-cancel-coordination-') as directory:
                        completed = threading.Event()
                        timing = {}
                        with pytest.MonkeyPatch.context() as patch:
                            patch.setenv('DEPLOYMENT_ENV', 'test')
                            patch.setenv('ENABLE_V1_CATALOGUE', 'true')
                            patch.setenv('ENABLE_V1_CATALOGUE_BROWSER', 'true')
                            response = original.routes.snapshots_response

                            def measured(*call_args, **call_kwargs):
                                timing['worker_start'] = time.perf_counter()
                                timing['worker_thread'] = threading.get_ident()
                                try:
                                    value = response(*call_args, **call_kwargs)
                                    timing['status_code'] = value.status_code
                                    return value
                                finally:
                                    timing['worker_end'] = time.perf_counter()
                                    completed.set()

                            patch.setattr(original.routes, 'snapshots_response', measured)
                            started, cpu = time.perf_counter(), time.thread_time()
                            try:
                                funcs[mode](Path(directory), patch, cancel)
                            except BaseException as exc:
                                result = {'outcome': 'failed', 'error_type': type(exc).__name__, 'error': str(exc)}
                            else:
                                result = {'outcome': 'passed'}
                            elapsed, main_cpu = time.perf_counter() - started, time.thread_time() - cpu
                            # Native cancellation can leave the real worker live.
                            # Never remove its temporary sealed files before it
                            # has actually completed, even when original polling
                            # exceeded the unchanged five-second bound.
                            worker_finished = completed.wait(5)
                            result.update(mode=mode, cancel=cancel, iteration=iteration,
                                elapsed_s=elapsed, main_thread_cpu_s=main_cpu,
                                worker_finished_before_temp_cleanup=worker_finished,
                                worker_elapsed_s=timing.get('worker_end', time.perf_counter()) - timing.get('worker_start', started),
                                status_code=timing.get('status_code'), worker_thread=timing.get('worker_thread'))
                            results.append(result)
                            print(json.dumps(result), flush=True)
    finally:
        if cov:
            cov.stop()
        sys.setswitchinterval(switch_before)
    after = hashes()
    report = {'version': 'c22-read-only-cancellation-coordination-diagnosis-v1',
        'qualification': 'Actual route and configured sealed synthetic service; alternative test coordination compiled only in memory. Python thread switch interval is a deliberate stress parameter, not asserted to match hosted CI.',
        'switch_interval_before': switch_before, 'stress_switch_interval': args.switch_interval,
        'application_coverage_enabled': args.coverage,
        'versions': {name: importlib.metadata.version(name) for name in ['anyio', 'starlette', 'fastapi', 'coverage']},
        'original_function_sha256': hashlib.sha256(source.encode()).hexdigest(),
        'candidate_function_sha256': hashlib.sha256(alternate.encode()).hexdigest(),
        'candidate_function': alternate, 'source_before_sha256': before, 'source_after_sha256': after,
        'source_unchanged': before == after, 'results': results}
    with output.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'output': str(output.relative_to(ROOT)), 'source_unchanged': before == after,
        'original_failures': sum(item['mode'] == 'original' and item['outcome'] != 'passed' for item in results),
        'candidate_failures': sum(item['mode'] == 'event' and item['outcome'] != 'passed' for item in results)}))


if __name__ == '__main__':
    main()
