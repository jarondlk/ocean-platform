"""An isolated full100k traversal measurement through actual catalogue boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.environ.get('RUN_C26_SCALE_ACCEPTANCE') != '1',
    reason='C26 full traversal runs in its explicit isolated CI step')
def test_full_scale_api_agent_controller_membership_and_lab_budget(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / 'scale.json'
    environment = dict(os.environ, DEPLOYMENT_ENV='test', AUTH_MODE='disabled',
        ENABLE_V1_CATALOGUE='true', ENABLE_V1_RESEARCH_CONTROLLER='true')
    subprocess.run([sys.executable, '-m', 'tests.system_acceptance_scale_support',
        '--output', str(output)], cwd=root, env=environment, check=True, timeout=240)
    report = json.loads(output.read_text())
    assert report['fixture']['population'] == 100_000
    assert report['fixture']['live_calls_performed'] is False
    assert all(item['status'] == 'passed' for item in report['checks']), report['checks']
