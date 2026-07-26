"""Stream-parse teaching answers into closed sections as the LLM writes.

Emits ``section_draft`` SSE events when a section is complete (next heading
appears or the stream ends) so the Answer tab can paint progressively and
Visual Summary can reuse pre-split sections.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from app.agents.main.runner.events import EventCallback, _emit
from app.agents.visual_summary.planning.study_sheet import is_topic_study_sheet_goal

# Prefer markdown headings so "1. Do step" body lines are not treated as sections.
# ## 1. Title  |  # 1. Title  |  **1. Title**
_HEADING = re.compile(
    r"(?m)^(?:"
    r"#{1,4}\s+(\d+)\s*[.):\-–—]\s*(.+?)\s*$"
    r"|"
    r"\*\*(\d+)\s*[.):\-–—]\s*(.+?)\*\*\s*$"
    r")"
)

EmitFn = Callable[[dict[str, Any]], None]


def should_stream_sections(goal: str, *, text_so_far: str = "") -> bool:
    """True for study-sheet / deep-teach goals, or when answer already looks numbered."""
    g = (goal or "").strip()
    if is_topic_study_sheet_goal(g):
        return True
    if re.search(r"\b(explain|teach|learn|study\s*sheet|walk\s*me\s*through)\b", g, re.I):
        return True
    # Mid-stream: answer already has numbered sections
    if text_so_far and len(_HEADING.findall(text_so_far)) >= 2:
        return True
    return False


def _section_body_parts(body: str) -> tuple[str, list[str]]:
    """Split body into prose body + bullet lines."""
    bullets: list[str] = []
    prose: list[str] = []
    for line in (body or "").splitlines():
        m = re.match(r"^[\s]*(?:[-•*]|\d+[.)])\s+(.+)$", line)
        if m:
            b = m.group(1).strip()
            if b:
                bullets.append(b[:400])
        else:
            if line.strip():
                prose.append(line.rstrip())
    body_text = "\n".join(prose).strip()
    return body_text, bullets


def parse_closed_sections(text: str) -> list[dict[str, Any]]:
    """
    Parse all fully delimited sections from markdown-ish text.

    The last heading's body is included only when the stream is finished
    (caller should pass complete text). For streaming, use SectionStreamTracker.
    """
    matches = list(_HEADING.finditer(text or ""))
    if not matches:
        return []
    out: list[dict[str, Any]] = []
    for i, m in enumerate(matches):
        num, title = _heading_parts(m)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body_raw = text[start:end].strip()
        body, bullets = _section_body_parts(body_raw)
        if not body and not bullets:
            continue
        out.append(
            {
                "index": num,
                "heading": f"{num}. {title}"[:200],
                "title": title[:160],
                "body": body[:2000],
                "bullets": bullets[:16],
            }
        )
    return out


def _heading_parts(m: re.Match[str]) -> tuple[int, str]:
    """Unpack ## N. or **N.** heading groups."""
    if m.group(1) is not None:
        num = int(m.group(1))
        title = m.group(2) or ""
    else:
        num = int(m.group(3))
        title = m.group(4) or ""
    title = re.sub(r"\s+", " ", title.strip())
    return num, title


class SectionStreamTracker:
    """Feed accumulating answer text; emit each section once when closed."""

    def __init__(
        self,
        *,
        on_event: EventCallback = None,
        run_id: str = "",
        goal: str = "",
    ) -> None:
        self._on_event = on_event
        self._run_id = run_id
        self._goal = goal
        self._emitted: set[int] = set()
        self._sections: list[dict[str, Any]] = []
        self._last_text = ""
        self._enabled: bool | None = None

    @property
    def sections(self) -> list[dict[str, Any]]:
        return list(self._sections)

    def feed(self, text: str) -> list[dict[str, Any]]:
        """Ingest full answer so far; emit newly closed sections. Returns newly closed."""
        self._last_text = text or ""
        if self._enabled is None:
            self._enabled = should_stream_sections(self._goal, text_so_far=self._last_text)
        elif not self._enabled and should_stream_sections(
            self._goal, text_so_far=self._last_text
        ):
            self._enabled = True
        if not self._enabled:
            return []

        matches = list(_HEADING.finditer(self._last_text))
        if len(matches) < 2:
            # Need the next heading to close the previous section.
            return []

        newly: list[dict[str, Any]] = []
        # All but last heading are closed.
        for i, m in enumerate(matches[:-1]):
            num, title = _heading_parts(m)
            if num in self._emitted:
                continue
            start = m.end()
            end = matches[i + 1].start()
            body_raw = self._last_text[start:end].strip()
            body, bullets = _section_body_parts(body_raw)
            if not body and not bullets:
                continue
            sec = {
                "index": num,
                "heading": f"{num}. {title}"[:200],
                "title": title[:160],
                "body": body[:2000],
                "bullets": bullets[:16],
            }
            self._emitted.add(num)
            self._sections.append(sec)
            newly.append(sec)
            self._emit_section(sec, phase="closed")
        return newly

    def finish(self, text: str | None = None) -> list[dict[str, Any]]:
        """Flush the final open section when the stream ends."""
        if text is not None:
            self._last_text = text
        if self._enabled is None:
            self._enabled = should_stream_sections(self._goal, text_so_far=self._last_text)
        if not self._enabled or not self._last_text.strip():
            return []

        matches = list(_HEADING.finditer(self._last_text))
        newly: list[dict[str, Any]] = []
        if not matches:
            return []

        # Emit any remaining closed + the last open section.
        for i, m in enumerate(matches):
            num, title = _heading_parts(m)
            if num in self._emitted:
                continue
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(self._last_text)
            body_raw = self._last_text[start:end].strip()
            body, bullets = _section_body_parts(body_raw)
            if not body and not bullets:
                continue
            sec = {
                "index": num,
                "heading": f"{num}. {title}"[:200],
                "title": title[:160],
                "body": body[:2000],
                "bullets": bullets[:16],
            }
            self._emitted.add(num)
            self._sections.append(sec)
            newly.append(sec)
            self._emit_section(sec, phase="final" if i == len(matches) - 1 else "closed")

        if newly or self._sections:
            _emit(
                self._on_event,
                "section_stream_complete",
                run_id=self._run_id,
                section_count=len(self._sections),
                sections=self._sections,
            )
        return newly

    def _emit_section(self, sec: dict[str, Any], *, phase: str) -> None:
        _emit(
            self._on_event,
            "section_draft",
            run_id=self._run_id,
            phase=phase,
            index=sec["index"],
            heading=sec["heading"],
            title=sec["title"],
            body=sec.get("body") or "",
            bullets=sec.get("bullets") or [],
            section_count=len(self._sections),
        )

    def as_structured_sections(self) -> list[dict[str, Any]]:
        """Shape compatible with handoff structured.sections."""
        return [
            {
                "heading": s["heading"],
                "body": s.get("body") or "",
                "bullets": list(s.get("bullets") or []),
            }
            for s in self._sections
        ]


def attach_streamed_sections_to_run(run: Any, tracker: SectionStreamTracker) -> None:
    """Persist pre-split sections on the run for Visual Summary handoff."""
    sections = tracker.as_structured_sections()
    if not sections:
        return
    run._streamed_sections = sections  # type: ignore[attr-defined]
    opts = dict(run.run_options or {}) if isinstance(run.run_options, dict) else {}
    opts["streamed_sections"] = sections
    opts["streamed_section_count"] = len(sections)
    run.run_options = opts


def maybe_paint_early_visual(
    db: Any,
    run: Any,
    tracker: SectionStreamTracker,
    *,
    on_event: EventCallback = None,
    force_complete: bool = False,
) -> None:
    """Assemble study-board panels from streamed sections (non-blocking best-effort)."""
    sections = tracker.as_structured_sections()
    if len(sections) < 1:
        return
    attach_streamed_sections_to_run(run, tracker)
    try:
        from app.agents.main.runner.early_visual import refresh_early_visual

        refresh_early_visual(
            db,
            run,
            sections=sections,
            on_event=on_event,
            force_complete=force_complete,
        )
    except Exception:
        pass
