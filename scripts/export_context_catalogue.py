"""Generate the C08 Python-owned shared JSON Schema deterministically."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pydantic import TypeAdapter
from schema import context_catalogue
from schema.context_catalogue import CatalogueContract, ContractModel

TARGET = ROOT / 'schema' / 'context_catalogue.v1.schema.json'


def schema_text() -> str:
    schema = CatalogueContract.model_json_schema()
    for model in vars(context_catalogue).values():
        if isinstance(model, type) and issubclass(model, ContractModel):
            definition = schema.get('$defs', {}).get(model.__name__)
            if definition is not None:
                for name, field in model.model_fields.items():
                    if field.default_factory is not None:
                        default = field.get_default(call_default_factory=True)
                        definition['properties'][name]['default'] = TypeAdapter(field.annotation).dump_python(default, mode='json')
    for name in ('ScopeCompatibility', 'ScopeEvidence'):
        schema['$defs'][name]['additionalProperties'] = False
    schema['$defs']['ScopeCompatibility']['required'].append('version')
    schema['x-source-aliases'] = context_catalogue.ALIASES
    schema['x-dataset-sections'] = list(context_catalogue.DATASET_SECTIONS)
    schema['x-schema-version'] = context_catalogue.SCHEMA_VERSION
    schema['$defs']['ScopeCompatibility']['properties']['version']['const'] = context_catalogue.PUBLICATION_SCOPE_VERSION
    schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    schema['$id'] = 'urn:ocean:context-catalogue:v1'
    return json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail if checked-in schema differs')
    args = parser.parse_args()
    expected = schema_text()
    if args.check:
        if not TARGET.exists() or TARGET.read_text() != expected:
            print('Context catalogue schema is stale; run scripts/export_context_catalogue.py', file=sys.stderr)
            return 1
        print('Context catalogue schema is current')
    else:
        TARGET.write_text(expected)
        print(f'Wrote {TARGET.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
