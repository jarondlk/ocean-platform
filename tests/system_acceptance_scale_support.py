"""C26 100k boundary traversal; explicit synthetic backend, real API/tools/controller.

This is not a 100k C17/scientific materialization or production throughput claim.
The isolated-process lab bounds are declared before measurement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

from api.catalogue_routes import _worker_response
from orchestration.catalogue_tools import CatalogueTools, invoke_catalogue
from orchestration.catalogue_service import CatalogueService
from orchestration.research_controller import ResearchController
from schema.catalogue_service import CatalogueListRequest
from schema.context_catalogue_fixtures import fixture_scope, make_catalogue
from tests.catalogue_service_support import fixture_user, synthetic_service
from tests.test_research_controller_scale import ExplicitSubmissionLoader

MAX_WALL_SECONDS = 180
MAX_RSS_MIB = 3072


def _hash(values):
    return hashlib.sha256(json.dumps(values, separators=(',', ':'), sort_keys=True).encode()).hexdigest()


def run_scale_acceptance():
    started = time.monotonic()
    count, hidden, page_limit = 100_000, 'synthetic:dataset:001234', 500
    snapshot = hashlib.sha256(b'C26 explicit synthetic 100000 catalogue').hexdigest()
    catalogue, resolver, _ = synthetic_service(catalogue=make_catalogue(count, snapshot_id=snapshot))
    # Exercise the unchanged default-four-view cache after the approved C14
    # optimization. Both original negative memory profiles remain immutable.
    service = CatalogueService(resolver=resolver, maximum_cached_views=4)
    user = fixture_user('c26-scale-owner')
    resolver.revoke(user, hidden)
    tools = CatalogueTools(service, lambda: user)
    base = {'snapshot_id': snapshot, 'scope': fixture_scope().model_dump(mode='json'),
        'filters': {'kinds': ['dataset']}, 'limit': page_limit}
    expected_ids = [f'synthetic:dataset:{index:06d}' for index in range(count) if index != 1234]
    actual_ids, cursor, seen_cursors, pages, first_cursor = [], None, set(), 0, None
    parity, totals = True, True
    while True:
        request = {**base, 'cursor': cursor}
        human = _worker_response(service, 'catalogue.list', CatalogueListRequest.model_validate(request), user)
        human_body = json.loads(human.body)
        agent_body = tools.list(request)
        parity = parity and human.status_code == 200 and human_body == agent_body
        if human.status_code != 200:
            break
        totals = totals and human_body['total']['value'] == count - 1
        actual_ids.extend(item['id'] for item in human_body['items'])
        pages += 1
        cursor = human_body['next_cursor']
        first_cursor = first_cursor or cursor
        if cursor is None:
            break
        if cursor in seen_cursors or pages > count // page_limit + 1:
            raise ValueError('Scale traversal repeated a cursor or exceeded its full-population bound')
        seen_cursors.add(cursor)
    loader = ExplicitSubmissionLoader(catalogue, service, user)
    controller_counts = []
    for preview in (100, 500):
        controller = ResearchController(investigations=loader, catalogue=service,
            identity_provider=lambda: user, limits={'observation_preview_rows': preview})
        result = controller.execute({**loader.request, 'question': 'Count all datasets'})
        controller_counts.append({'outcome': result.outcome,
            'count': result.observations[0].counts[0].value,
            'model_calls': result.budget.model_calls, 'tool_actions': result.budget.tool_actions})
    later_targets = ['synthetic:dataset:000025', 'synthetic:dataset:000501', 'synthetic:dataset:099999']
    later_actual = []
    for identity in later_targets:
        response = tools.list({**base, 'filters': {'kinds': ['dataset'], 'search': identity}, 'limit': 1})
        later_actual.extend(item['id'] for item in response['items'])
    other = fixture_user('c26-scale-other')
    stale_owner = invoke_catalogue(service, 'catalogue.list', {**base, 'cursor': first_cursor}, lambda: other)
    resolver.revoke(user, hidden, 'synthetic:dataset:000025')
    # MutableFixtureResolver.revoke is a one-change fixture; a second policy
    # mutation must supply a new revision under the host resolver contract.
    resolver.revisions[user.id] = 'permissions-3'
    stale_policy = invoke_catalogue(service, 'catalogue.list', {**base, 'cursor': first_cursor}, lambda: user)
    elapsed = time.monotonic() - started
    memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 ** 2 if sys.platform == 'darwin' else 1024)
    expected = {'members': count - 1, 'pages': 200, 'human_agent_equal': True,
        'all_members_equal': True, 'whole_scope_totals': True,
        'controller_counts': [{'outcome': 'completed', 'count': count - 1, 'model_calls': 0, 'tool_actions': 1}] * 2,
        'late_targets': later_targets, 'cross_owner_cursor': 409, 'stale_policy_cursor': 409}
    observed = {'members': len(actual_ids), 'pages': pages, 'human_agent_equal': parity,
        'all_members_equal': actual_ids == expected_ids, 'whole_scope_totals': totals,
        'controller_counts': controller_counts, 'late_targets': later_actual,
        'cross_owner_cursor': stale_owner[0], 'stale_policy_cursor': stale_policy[0]}
    checks = [{'id': 'catalogue-full-scale-parity', 'status': 'passed' if observed == expected else 'failed',
        'owner_components': ['C08', 'C14', 'C16', 'C19', 'C26'], 'expected': expected, 'observed': observed,
        'evidence': {'inventory_sha256': _hash(actual_ids), 'expected_inventory_sha256': _hash(expected_ids)}}]
    checks.append({'id': 'catalogue-scale-lab-budget',
        'status': 'passed' if elapsed <= MAX_WALL_SECONDS and memory <= MAX_RSS_MIB else 'failed',
        'owner_components': ['C14', 'C26'],
        'expected': {'wall_seconds_max': MAX_WALL_SECONDS, 'isolated_process_peak_rss_mib_max': MAX_RSS_MIB},
        'observed': {'wall_seconds': elapsed, 'isolated_process_peak_rss_mib': memory},
        'evidence': {'classification': 'isolated-process synthetic lab measurement; no production capacity claim'}})
    return {'version': 'c26-scale-observations-v1', 'fixture': {'classification': 'synthetic-local-actual-services',
        'snapshot_id': snapshot, 'population': count, 'excluded_canonical_id': hidden,
        'context_qualification': 'Explicit synthetic frozen loader; not C17 scientific snapshot capacity',
        'maximum_cached_views': 4,
        'live_calls_performed': False}, 'checks': checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run_scale_acceptance()
    with args.output.open('x') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
