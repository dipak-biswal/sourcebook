"""Agent profile tool sets."""

import uuid
from unittest.mock import MagicMock

from app.agents.profiles import get_profile, normalize_agent_type
from app.agents.tools import build_tools


def test_general_profile_has_workspace_tools():
    profile = get_profile("general")
    assert profile.agent_type == "general"
    assert "study_guide" not in profile.tool_names
    assert "search_documents" in profile.tool_names
    assert "create_note" in profile.tool_names


def test_normalize_agent_type_always_general():
    assert normalize_agent_type("bogus") == "general"
    assert normalize_agent_type("study_guide") == "general"
    assert normalize_agent_type(None) == "general"


def test_build_tools_single_profile():
    db = MagicMock()
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    general = {
        t.name
        for t in build_tools(
            db, workspace_id=ws_id, user_id=user_id, agent_type="general"
        )
    }
    legacy = {
        t.name
        for t in build_tools(
            db, workspace_id=ws_id, user_id=user_id, agent_type="study_guide"
        )
    }
    assert "study_guide" not in general
    assert general == legacy
    assert "create_note" in general