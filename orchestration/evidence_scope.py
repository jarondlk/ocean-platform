"""Conservative eligibility checks for supplementary, precomputed evidence."""
from __future__ import annotations

from datetime import datetime, timezone

SCOPE_KEYS = (
    'source_type', 'bay', 'sample_id', 'time_from', 'time_to', 'provider',
    'provider_project_id', 'provider_run_id', 'assignment_method', 'taxon',
    'sample_kind', 'is_control', 'lat_min', 'lat_max', 'lon_min', 'lon_max', 'analysis_id',
)


def explicit_scope(scope: dict) -> dict:
    return {key: scope[key] for key in SCOPE_KEYS if scope.get(key) is not None}


def _date(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (ValueError, TypeError):
        return None


def context_matches_scope(document: dict, scope: dict) -> bool:
    """Unknown scope is insufficient for a filtered query; never infer from prose.

    Aggregate date ranges must be wholly contained, since an overlapping aggregate
    cannot be recomputed for a smaller interval by the language model.
    """
    metadata = document.get('metadata') or {}
    values = {**metadata, **document}
    for key, expected in explicit_scope(scope).items():
        if key == 'source_type':
            family = values.get('source_family') or values.get('source_type')
            covered = values.get('covered_source_types') or ([family] if family else [])
            if not covered or any(value != expected for value in covered):
                return False
        elif key in ('time_from', 'time_to'):
            start = _date(values.get('time_from') or values.get('time') or values.get('date'))
            end_value = values.get('time_to') or values.get('time') or values.get('date')
            end = _date(end_value)
            if end and len(str(end_value)) == 10:
                end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
            limit = _date(expected)
            if not start or not end or not limit or start > end:
                return False
            # Date-only upper bounds include that calendar day.
            if key == 'time_to' and len(str(expected)) == 10:
                limit = limit.replace(hour=23, minute=59, second=59, microsecond=999999)
            if (key == 'time_from' and start < limit) or (key == 'time_to' and end > limit):
                return False
        elif key in ('lat_min', 'lat_max', 'lon_min', 'lon_max'):
            coordinate = values.get(key, values.get(key[:3]))
            if coordinate is None:
                return False
            try:
                if key.endswith('min') and not float(coordinate) >= float(expected):
                    return False
                if key.endswith('max') and not float(coordinate) <= float(expected):
                    return False
            except (ValueError, TypeError):
                return False
        elif values.get(key) != expected:
            return False
    return True
