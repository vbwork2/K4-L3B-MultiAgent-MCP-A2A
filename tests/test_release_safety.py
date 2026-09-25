import subprocess
from pathlib import Path

import pytest


def test_repository_contains_no_competition_payload() -> None:
    root = Path(__file__).resolve().parents[1]
    if not (root / ".git").exists():
        pytest.skip("release safety check requires a Git worktree")
    tracked = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--",
            "case-set.json",
            "inputs",
            "outputs",
            ".env",
            "oracles",
            "reference-outputs",
            "private-partitions.json",
            "mcp-access.json",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert [path for path in tracked if not path.endswith("/.gitkeep")] == []


def test_example_environment_has_no_real_key() -> None:
    root = Path(__file__).resolve().parents[1]
    content = (root / ".env.example").read_text(encoding="utf-8")
    assert "sk-team-replace_me" in content
    assert content.count("sk-team-") == 1
