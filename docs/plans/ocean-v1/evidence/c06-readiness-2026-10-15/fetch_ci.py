"""Read this repository's push CI using its existing Git authentication in memory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('commit')
    parser.add_argument('--output', default='hosted-ci.json')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.commit):
        raise ValueError('Expected a full commit SHA')
    credential = subprocess.run(
        ['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
        text=True, capture_output=True, check=True,
    )
    fields = dict(line.split('=', 1) for line in credential.stdout.splitlines() if '=' in line)
    token = fields.get('password')
    if not token:
        raise RuntimeError('Existing Git authentication is unavailable')
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28'}
    base = 'https://api.github.com/repos/jarondlk/ocean-platform'

    def fetch(path):
        with urlopen(Request(base + path, headers=headers), timeout=30) as response:
            return json.load(response)

    runs = fetch(f'/actions/runs?head_sha={args.commit}&event=push&per_page=20')['workflow_runs']
    runs = [item for item in runs if item['head_sha'] == args.commit and item['name'] == 'CI']
    if not runs:
        print(json.dumps({'source_commit': args.commit, 'status': 'not_created_yet'}))
        return
    run = max(runs, key=lambda item: item['id'])
    jobs = fetch(f"/actions/runs/{run['id']}/jobs?per_page=100")['jobs']
    receipt = {'source_commit': args.commit,
               'run': {key: run.get(key) for key in ('id', 'html_url', 'status', 'conclusion',
                                                   'event', 'head_sha', 'run_attempt')},
               'jobs': [{key: job.get(key) for key in ('id', 'name', 'status', 'conclusion', 'steps')}
                        for job in jobs]}
    output = Path(__file__).resolve().parent / args.output
    output.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'source_commit': args.commit, 'run': receipt['run'],
                      'jobs': [{key: job[key] for key in ('id', 'name', 'status', 'conclusion')}
                               for job in receipt['jobs']]}))


if __name__ == '__main__':
    main()
