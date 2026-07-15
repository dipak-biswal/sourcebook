"""Agent profile tool sets."""

import uuid
from unittest.mock import MagicMock

from app.agents.profiles import agent_system_prompt, get_profile, normalize_agent_type
from app.agents.tools import build_tools


def test_general_profile_has_workspace_tools():
    profile = get_profile("general")
    assert profile.agent_type == "general"
    assert "study_guide" not in profile.tool_names
    assert "search_documents" in profile.tool_names
    assert "web_search" in profile.tool_names
    assert "create_note" in profile.tool_names
    assert "get_current_date" in profile.tool_names


def test_agent_system_prompt_uses_date_tool_not_hardcoded_header():
    prompt = agent_system_prompt()
    assert "TODAY:" not in prompt
    assert "get_current_date" in prompt
    assert "FIRST tool call" in prompt
    assert "outdated years" in prompt
    assert "list_documents" in prompt
    assert "web_search" in prompt
    # Generic template — no resume/ATS vertical hardcoding
    assert "resume" not in prompt.lower()
    assert "ats" not in prompt.lower()
    assert "gap analysis vs a target role" not in prompt.lower()


def test_build_tools_can_disable_web_search():
    db = MagicMock()
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    with_web = {
        t.name
        for t in build_tools(
            db, workspace_id=ws_id, user_id=user_id, agent_type="general"
        )
    }
    no_web = {
        t.name
        for t in build_tools(
            db,
            workspace_id=ws_id,
            user_id=user_id,
            agent_type="general",
            allow_web_search=False,
        )
    }
    assert "web_search" in with_web
    assert "web_search" not in no_web
    assert "search_documents" in no_web


def test_build_tools_orders_date_first():
    db = MagicMock()
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    tools = build_tools(
        db, workspace_id=ws_id, user_id=user_id, agent_type="general"
    )
    assert tools[0].name == "get_current_date"


def test_normalize_agent_type_always_general():
    assert normalize_agent_type("bogus") == "general"
    assert normalize_agent_type("study_guide") == "general"
    assert normalize_agent_type(None) == "general"


def test_visual_summary_profile_has_layout_tools():
    profile = get_profile("visual_summary")
    assert profile.agent_type == "visual_summary"
    assert profile.tool_names == frozenset(
        {"plan_layout", "render_ui", "get_current_date"}
    )


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
    assert "web_search" in general
    assert "create_note" in general
    assert "get_current_date" in general