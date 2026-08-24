"""Cross-platform invariants for hash-locked deployment dependencies."""
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _locked_version(requirements: str, package: str) -> tuple[int, ...]:
    """Return one explicitly pinned package version from requirements text."""
    prefix = f"{package}=="
    matches = [
        line.removeprefix(prefix).split()[0]
        for line in requirements.splitlines()
        if line.startswith(prefix)
    ]
    assert len(matches) == 1
    return tuple(int(part) for part in matches[0].split("."))


def test_linux_sqlalchemy_greenlet_dependency_is_explicitly_locked() -> None:
    """Apple Silicon lock generation must retain the Linux Cloud Run extra."""
    runtime_input = (PROJECT_ROOT / "requirements/runtime.in").read_text()
    runtime_lock = (PROJECT_ROOT / "requirements/runtime.txt").read_text()
    dev_lock = (PROJECT_ROOT / "requirements/dev.txt").read_text()

    assert "greenlet==3.5.5" in runtime_input
    assert "greenlet==3.5.5" in runtime_lock
    assert "greenlet==3.5.5" in dev_lock


def test_archive_gitpython_security_floor_is_explicitly_locked() -> None:
    """Keep the archived Streamlit app above the GitPython advisory range."""
    archive_input = (PROJECT_ROOT / "requirements/archive.in").read_text()
    archive_lock = (PROJECT_ROOT / "requirements/archive.txt").read_text()

    input_version = _locked_version(archive_input, "gitpython")
    lock_version = _locked_version(archive_lock, "gitpython")

    assert input_version == lock_version
    assert input_version >= (3, 1, 58)
