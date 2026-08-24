"""Cross-platform invariants for hash-locked deployment dependencies."""
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_linux_sqlalchemy_greenlet_dependency_is_explicitly_locked() -> None:
    """Apple Silicon lock generation must retain the Linux Cloud Run extra."""
    runtime_input = (PROJECT_ROOT / "requirements/runtime.in").read_text()
    runtime_lock = (PROJECT_ROOT / "requirements/runtime.txt").read_text()
    dev_lock = (PROJECT_ROOT / "requirements/dev.txt").read_text()

    assert "greenlet==3.5.5" in runtime_input
    assert "greenlet==3.5.5" in runtime_lock
    assert "greenlet==3.5.5" in dev_lock
