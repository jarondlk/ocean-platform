"""Run the retained PG red probe with exact pinned, unchanged Git-baseline code."""
import hashlib
import subprocess
import sys
import types


def pytest_collection_modifyitems(items):
    for item in items:
        if item.name != "test_baseline_stale_orm_selection_reproduces_committed_hold_loss":
            continue
        revision = "516b08675460b7de7b02ecafeec0e2f359d38747"
        raw = subprocess.check_output(["git", "show", revision + ":db/retention.py"])
        old = types.ModuleType("c03_exact_git_baseline")
        sys.modules[old.__name__] = old
        exec(compile(raw, revision + ":db/retention.py", "exec"), old.__dict__)

        def actual_baseline(database):
            old.get_session = database.session_context
            report = old.cleanup_chat_interactions(retention_days=90, dry_run=False, now=item.module.NOW)
            return report.eligible_count, report.deleted_count

        item.module.legacy_selection_cleanup = actual_baseline
        print("Exact baseline revision:", revision)
        print("Exact baseline db/retention.py SHA256:", hashlib.sha256(raw).hexdigest())
