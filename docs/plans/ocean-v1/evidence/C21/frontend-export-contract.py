"""Export C21 browser models/schema from the authoritative Python public models."""
from pathlib import Path
import json
import sys
from pydantic.json_schema import models_json_schema
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from scripts.export_catalogue_types import typescript
from schema.research_evidence import EVIDENCE_REQUEST_MODELS, EVIDENCE_RESPONSE_MODELS, ANSWER_REQUEST_MODELS, ANSWER_RESPONSE_MODELS
models = list(dict.fromkeys([*EVIDENCE_REQUEST_MODELS.values(), *EVIDENCE_RESPONSE_MODELS.values(), *ANSWER_REQUEST_MODELS.values(), *ANSWER_RESPONSE_MODELS.values()]))
_, schema = models_json_schema([(model, 'validation') for model in models])
result = '// Generated from schema/research_evidence.py; do not edit by hand.\n'
for name, definition in schema['$defs'].items():
    result += f'export type {name} = {typescript(definition)};\n\n'
result += 'export type EvidenceModels = {\n' + ''.join(f'  {json.dumps(name)}: {name};\n' for name in schema['$defs']) + '};\n'
result += 'export const evidenceContractSchema = ' + json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2) + ' as const;\n'
target = ROOT / 'frontend-v1/src/research-evidence.generated.ts'
if '--check' in sys.argv:
    assert target.read_text() == result, 'C21 browser schema/types are stale'
else:
    target.write_text(result)
print('C21 browser schema/types are current')
