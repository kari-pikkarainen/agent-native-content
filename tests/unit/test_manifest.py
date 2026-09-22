"""Tests for experiment manifest environment capture."""

import subprocess
from pathlib import Path

from contextbench.experiments import manifest
from contextbench.experiments.manifest import current_git_commit, current_git_dirty


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


class _CompletedGit:
    """Minimal stand-in for the CompletedProcess the manifest module reads."""

    def __init__(self, stdout: str) -> None:
        self.stdout = stdout


def test_dirty_worktree_is_recorded(monkeypatch) -> None:
    commands: list[list[str]] = []

    def porcelain_line(command: list[str], **_kwargs: object) -> _CompletedGit:
        commands.append(command)
        return _CompletedGit(" M src/contextbench/experiments/manifest.py\n")

    monkeypatch.setattr(subprocess, "run", porcelain_line)
    assert current_git_dirty() is True
    assert commands == [["git", "status", "--porcelain"]]

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: _CompletedGit(""),
    )
    assert current_git_dirty() is False


def test_missing_git_reports_dirty(monkeypatch) -> None:
    def missing_git(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", missing_git)

    assert current_git_dirty() is True

    def failing_git(*args: object, **kwargs: object) -> None:
        raise subprocess.CalledProcessError(128, ["git", "status", "--porcelain"])

    monkeypatch.setattr(subprocess, "run", failing_git)

    assert current_git_dirty() is True


def test_supplied_commit_skips_the_worktree_check(monkeypatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("a caller-supplied commit must not inspect the worktree")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(manifest, "current_git_commit", forbidden)
    monkeypatch.setattr(manifest, "current_git_dirty", forbidden)

    assert manifest.resolve_git_state(
        git_commit="c" * 40,
        git_dirty=None,
        allow_dirty=False,
    ) == ("c" * 40, False)
