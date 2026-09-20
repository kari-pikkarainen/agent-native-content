"""Tests for experiment manifest environment capture."""

import subprocess
from pathlib import Path

from contextbench.experiments.manifest import current_git_commit


def test_current_git_commit_falls_back_to_loose_head(
    monkeypatch,
    tmp_path: Path,
) -> None:
    commit = "a" * 40
    git_dir = tmp_path / ".git"
    (git_dir / "refs" / "heads").mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
    (git_dir / "refs" / "heads" / "main").write_text(f"{commit}\n")
    nested = tmp_path / "nested" / "directory"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    def fail_git(*args: object, **kwargs: object) -> None:
        raise subprocess.CalledProcessError(69, ["git", "rev-parse", "HEAD"])

    monkeypatch.setattr(subprocess, "run", fail_git)

    assert current_git_commit() == commit


def test_current_git_commit_falls_back_to_packed_head(
    monkeypatch,
    tmp_path: Path,
) -> None:
    commit = "b" * 40
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
    (git_dir / "packed-refs").write_text(
        f"# pack-refs with: peeled fully-peeled sorted\n{commit} refs/heads/main\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )

    assert current_git_commit() == commit
