"""Global test guards: never let tests reach live LLM endpoints.

A developer .env may carry a real OPENAI_API_KEY; these autouse patches force
the LLM-optional paths (extractor/profiler) off so every test is hermetic.
Tests that cover those paths re-enable the flags and mock the client.
"""

import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _no_live_llm(monkeypatch):
    monkeypatch.setattr(settings, "visual_summary_llm_extractor", False)
    monkeypatch.setattr(settings, "workspace_llm_profiler", False)
