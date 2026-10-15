"""Reproduce current endpoint acceptance against exact pre-C07 function source.

Only subprocess memory changes. The shared checkout and canonical files are never
rewritten. FastAPI keeps the same function objects; their code is the Git source.
"""
import ast
import csv
import io
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
import pytest
import api.main as main
import api.admin_feedback_routes as feedback
import api.edna_analysis_routes as analysis

revision = '824724b051b1039e811d25448d6b592755825ad2'
print(f'Pre-C07 revision: {revision}', flush=True)
for module, relative, names in (
    (main, 'api/main.py', ['data_edna_export']),
    (feedback, 'api/admin_feedback_routes.py', ['_csv_safe', 'export_admin_feedback']),
    (analysis, 'api/edna_analysis_routes.py', ['export']),
):
    source = subprocess.check_output(['git', 'show', f'{revision}:{relative}'], text=True)
    tree = ast.parse(source, filename=f'{revision}:{relative}')
    module.__dict__.update(csv=csv, io=io, json=json)
    for name in names:
        node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
        node.decorator_list = []
        original = getattr(module, name, None)
        exec(compile(ast.Module(body=[node], type_ignores=[]), f'{revision}:{relative}', 'exec'), module.__dict__)
        if original is not None:
            original.__code__ = getattr(module, name).__code__
            setattr(module, name, original)
        print(f'Restored function source: {relative}:{name}', flush=True)

raise SystemExit(pytest.main(['tests/test_api_edna_analysis.py', 'tests/test_admin_feedback.py', 'tests/test_api_edna.py', '-q', '--tb=short']))
