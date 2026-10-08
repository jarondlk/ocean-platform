"""Preflight or publish existing regional evidence with explicit user acceptance.

Reads retained, sealed analyses and their current canonical bindings. No provider
acquisition, database write, review-registry change or embedding is performed.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.immutable_bundle import atomic_json, digest
from ingestion.regional_publication import prepare_regional, publish_regional


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--decision', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if (any(p.is_symlink() for p in (args.decision, *args.decision.parents))
            or args.decision.stat().st_size > 16384
            or any(p.is_symlink() for p in (args.output, *args.output.parents))
            or args.output.resolve() == args.decision.resolve()):
        raise ValueError('Require separate bounded non-symlink input/output paths')
    decision = json.loads(args.decision.read_bytes())
    payload, period = prepare_regional(decision)
    report = {'publication_id': digest(payload), 'published': False,
              'days': len(period['observations']), 'gaps': period['final_series_gaps'],
              'analyses': payload['analyses'], 'provider_downloads': False,
              'database_writes': False, 'independent_researcher_approval': False,
              'provider_endorsement': False}
    if args.execute:
        report.update(publish_regional(decision), published=True)
    atomic_json(args.output, report)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
