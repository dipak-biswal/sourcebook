"""Agent run storage compact + prune."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.agents.run_storage import compact_json_value, compact_run_steps, prune_agent_runs


def test_compact_json_value_strips_heavy_keys():
    raw = {
        "status": "rendered",
        "prompt": "x" * 5000,
        "llm_output": '{"blocks":[]}',
        "block_count": 3,
        "spec": {"type": "generative_ui", "title": "T", "blocks": []},
    }
    out = compact_json_value(raw)
    assert out["status"] == "rendered"
    assert out["block_count"] == 3
    assert out["spec"]["type"] == "generative_ui"
    assert out["prompt"].startswith("[compacted")
    assert out["llm_output"].startswith("[compacted")


def test_compact_json_value_truncates_long_strings():
    out = compact_json_value("a" * 1000, max_str=50)
    assert len(out) == 50
    assert out.endswith("…")


def test_compact_run_steps_mutates_steps():
    step = SimpleNamespace(
        input={"prompt": "long " * 200, "notes": "ok"},
        output={"llm_output": {"a": 1}, "status": "planned"},
    )
    run = SimpleNamespace(steps=[step], status="completed")
    db = SimpleNamespace(flush=lambda: None)
    n = compact_run_steps(db, run)  # type: ignore[arg-type]
    assert n == 1
    assert str(step.input["prompt"]).startswith("[compacted")
    assert step.input["notes"] == "ok"
    assert step.output["status"] == "planned"


def test_prune_agent_runs_by_age():
    old = SimpleNamespace(
        id=uuid.uuid4(),
        status="completed",
        created_at=datetime.now(timezone.utc) - timedelta(days=60),
        user_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
    )
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value = q
    q.all.return_value = [old]
    db.query.return_value = q

    result = prune_agent_runs(
        db, user_id=old.user_id, retention_days=30, max_per_workspace=0
    )
    assert result["deleted_by_age"] == 1
    assert result["deleted_by_cap"] == 0
    db.delete.assert_called_once_with(old)
