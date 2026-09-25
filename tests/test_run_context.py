from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from student_agent import cli
from student_agent.cases import CaseSet
from student_agent.config import Settings


def test_resume_rejects_artifacts_without_matching_case_and_credential_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_set = CaseSet("v1", "l3b", ("CASE_001",), {"CASE_001": {"case_id": "CASE_001"}})
    settings = Settings(
        "https://competition.example",
        "sk-team-abcdefghijklmnop",
        "https://mcp.example/mcp",
        tmp_path,
    )
    monkeypatch.setattr(cli, "load_case_set", lambda root: case_set)
    monkeypatch.setattr(cli.Settings, "load", lambda root: settings)

    with pytest.raises(ValueError, match="run context changed"):
        asyncio.run(cli._run(tmp_path, resume=True))

    initial = cli._run_context_digest(case_set, settings)
    changed_case_set = CaseSet(
        "v1", "l3b", ("CASE_001",), {"CASE_001": {"case_id": "CASE_001", "topic": "new"}}
    )
    changed_key = Settings(
        settings.competition_api_url,
        "sk-team-1234567890abcdef",
        settings.mcp_endpoint,
        tmp_path,
    )
    assert initial != cli._run_context_digest(changed_case_set, settings)
    assert initial != cli._run_context_digest(case_set, changed_key)
