"""Agent profile tool sets."""

import uuid
from unittest.mock import MagicMock

from app.agents.profiles import get_profile, normalize_agent_type
from app.agents.tools import build_tools


def test_general_profile_excludes_study_guide():
    profile = get_profile("general")
    assert "study_guide" not in profile.tool_names
    assert "search_documents" in profile.tool_names


def test_study_guide_profile_includes_study_guide():
    profile = get_profile("study_guide")
    assert "study_guide" in profile.tool_names
    assert profile.default_max_steps == 4


def test_normalize_agent_type_defaults_unknown():
    assert normalize_agent_type("bogus") == "general"
    assert normalize_agent_type("study_guide") == "study_guide"


def test_build_tools_respects_profile():
    db = MagicMock()
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    general = {
        t.name
        for t in build_tools(
            db, workspace_id=ws_id, user_id=user_id, agent_type="general"
        )
    }
    study = {
        t.name
        for t in build_tools(
            db, workspace_id=ws_id, user_id=user_id, agent_type="study_guide"
        )
    }
    assert "study_guide" not in general
    assert "study_guide" in study
    assert "create_note" in general
    assert "create_note" in study