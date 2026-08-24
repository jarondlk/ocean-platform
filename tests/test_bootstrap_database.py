from __future__ import annotations

import scripts.bootstrap_database as bootstrap


def test_bootstrap_runs_migrations_before_corpus_initialization(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        bootstrap.command,
        "upgrade",
        lambda _configuration, revision: calls.append(f"alembic:{revision}"),
    )
    monkeypatch.setattr(
        bootstrap,
        "init_db",
        lambda: calls.append("init_db"),
    )
    monkeypatch.setattr(
        bootstrap,
        "database_status",
        lambda: {
            "ready": True,
            "vector_extension": True,
            "missing_tables": [],
            "table_count": len(bootstrap.REQUIRED_TABLES),
        },
    )

    status = bootstrap.bootstrap_database()

    assert calls == ["alembic:head", "init_db"]
    assert status["ready"] is True
