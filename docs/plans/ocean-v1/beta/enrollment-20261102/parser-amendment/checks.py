"""Focused mocked CLI dispatch/finalizer regression, no identity or DB work."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[6]


def run():
    spec = importlib.util.spec_from_file_location('enrollment_parser_amendment',
        ROOT / 'deploy/gcp/beta/enrollment/enroll.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    checks = []
    for arguments in [['--app'], ['--ap'], ['--app', '--role', 'admin', '--account-type', 'internal']]:
        captured = io.StringIO()
        with redirect_stdout(captured), \
                patch.object(module, 'configuration', side_effect=AssertionError('configuration forbidden')) as config, \
                patch.object(module, 'verify_identity', side_effect=AssertionError('identity/network forbidden')) as verify, \
                patch.object(module, 'enroll', side_effect=AssertionError('database forbidden')) as enroll, \
                patch.object(module, 'stop_proxy', side_effect=AssertionError('proxy/network forbidden')) as stop:
            code = module.main(arguments)
        assert code == 2 and json.loads(captured.getvalue())['state'] == 'failed'
        assert config.call_count == verify.call_count == enroll.call_count == stop.call_count == 0
        checks.append('abbreviated apply cannot enter configuration/identity/database/proxy: ' + arguments[0])
    for invalid_parser in [False, True]:
        captured = io.StringIO()
        with redirect_stdout(captured), \
                patch.object(module, 'configuration', side_effect=module.EnrollmentError('Controlled missing configuration')) as config, \
                patch.object(module, 'verify_identity', side_effect=AssertionError('identity forbidden')) as verify, \
                patch.object(module, 'enroll', side_effect=AssertionError('database forbidden')) as enroll, \
                patch.object(module, 'stop_proxy', return_value={'shutdown_requested': True}) as stop:
            code = module.main(['--apply', '--confirm-proj', 'not-accepted'] if invalid_parser else ['--apply'])
        assert code == 2 and stop.call_count == 1
        assert config.call_count == (0 if invalid_parser else 1)
        assert verify.call_count == enroll.call_count == 0
        assert json.loads(captured.getvalue())['proxy']['shutdown_requested']
        checks.append('exact apply still finalizes on ' + ('parser' if invalid_parser else 'configuration') + ' failure')
    captured = io.StringIO()
    with redirect_stdout(captured), \
            patch.object(module, 'configuration', side_effect=module.EnrollmentError('Controlled missing configuration')), \
            patch.object(module, 'stop_proxy', side_effect=OSError('controlled')) as stop:
        code = module.main(['--apply'])
    assert code == 3 and stop.call_count == 1
    assert json.loads(captured.getvalue())['state'] == 'failed_proxy_shutdown'
    checks.append('exact apply shutdown failure remains exit3 and unaccepted')
    return {'version': 'beta-enrollment-parser-regressions-v1', 'passed': len(checks),
        'checks': checks, 'identity_configuration_or_google_proof_used': False,
        'actual_network_db_or_proxy_calls': False, 'role_or_account_default_added': False,
        'original41_checks_repeated_or_retargeted': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = run()
    with args.output.open('x') as output:
        output.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'passed': result['passed'], 'actual_network_or_database_calls': False}))
