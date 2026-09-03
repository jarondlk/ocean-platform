"""UTC interval semantics shared by SQL, retrieval and research cohorts."""
from datetime import datetime, timedelta, timezone
import re


def utc_time(value: str) -> datetime:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ].+)?", value):
        raise ValueError("Time must be an ISO date or timestamp")
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (instant.replace(tzinfo=timezone.utc) if instant.tzinfo is None
            else instant.astimezone(timezone.utc))


def time_bounds(start=None, end=None):
    lower = utc_time(start) if start else None
    upper = utc_time(end) if end else None
    exclusive = bool(end and len(end) == 10)
    if exclusive:
        upper += timedelta(days=1)
    if lower and upper and (lower >= upper if exclusive else lower > upper):
        raise ValueError("time_from must not exceed time_to")
    return lower, upper, exclusive


def matches_time(value, start=None, end=None):
    lower, upper, exclusive = time_bounds(start, end)
    if lower is None and upper is None:
        return True
    if not value:
        return False
    try:
        instant = utc_time(str(value))
    except (ValueError, TypeError):
        return False
    if lower and (instant + timedelta(days=1) <= lower if len(str(value)) == 10 else instant < lower):
        return False
    return not (upper and (instant >= upper if exclusive else instant > upper))


def sql_time_conditions(column, start=None, end=None):
    """Column is a trusted code constant, never a request value."""
    if not re.fullmatch(r"[a-z_][a-z0-9_.]*", column):
        raise ValueError("Invalid time column")
    lower, upper, exclusive = time_bounds(start, end)
    value = (f"(CASE WHEN {column} ~ '[T ].*(Z|[+-][0-9]{{2}}(:?[0-9]{{2}})?)$' "
             f"THEN NULLIF({column}, '')::timestamptz ELSE NULLIF({column}, '')::timestamp AT TIME ZONE 'UTC' END)")
    clauses, params = [], {}
    if lower:
        clauses.append(f"({value} >= :utc_from OR (length({column}) = 10 AND {value} + INTERVAL '1 day' > :utc_from))")
        params['utc_from'] = lower
    if upper:
        clauses.append(f"{value} {'<' if exclusive else '<='} :utc_to")
        params['utc_to'] = upper
    return clauses, params
