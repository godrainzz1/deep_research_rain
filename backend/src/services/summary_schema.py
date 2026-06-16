"""Pydantic schema for task summary output validation and reformatting."""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field


class SummaryFinding(BaseModel):
    """A single finding within a task summary."""

    title: str = Field(..., description="Finding title, e.g. '多模态统一表示构筑感知基座'")
    meaning: str = Field(default="", description="Core meaning and value (1-2 sentences)")
    expansion: str = Field(default="", description="Multi-dimension analysis")


class TaskSummary(BaseModel):
    """Structured task summary output."""

    findings: list[SummaryFinding] = Field(default_factory=list, min_length=1, max_length=8)

    @classmethod
    def from_markdown(cls, text: str) -> Optional["TaskSummary"]:
        """Parse a Markdown task summary into structured form.

        Returns None if the text doesn't match the expected schema.
        """
        if not text or "暂无可用信息" in text:
            return None

        # Find findings: ### N. Title followed by content
        finding_pattern = re.compile(
            r"###\s*\d+\.?\s*(.+?)\n(.*?)(?=###\s*\d+\.?\s|\Z)", re.DOTALL
        )
        matches = finding_pattern.findall(text)

        if not matches:
            # Fallback: try plain "数字." or "关键发现" patterns
            alt_pattern = re.compile(
                r"(?:^|\n)\s*(?:\d+\.|关键发现\s*\d+[：:])\s*(.+?)\n(.*?)(?=(?:\n\s*(?:\d+\.|关键发现\s*\d+[：:]))|\Z)",
                re.DOTALL,
            )
            matches = alt_pattern.findall(text)

        findings: list[SummaryFinding] = []
        for title, body in matches:
            title = title.strip()
            body = body.strip()

            # Extract meaning and expansion from body
            meaning = ""
            expansion = ""

            meaning_match = re.search(r"\*\*含义[与和]价值\*\*[：:]\s*(.+?)(?=\n\s*\*\*|\Z)", body, re.DOTALL)
            if meaning_match:
                meaning = meaning_match.group(1).strip()

            expansion_match = re.search(r"\*\*多维度拓展\*\*[：:]\s*(.+?)(?=\Z)", body, re.DOTALL)
            if expansion_match:
                expansion = expansion_match.group(1).strip()

            if not meaning and not expansion:
                # No structured sub-fields found — use the whole body as meaning
                meaning = body

            findings.append(SummaryFinding(title=title, meaning=meaning, expansion=expansion))

        if not findings:
            return None

        return cls(findings=findings)

    def to_markdown(self) -> str:
        """Render the structured summary back to standardized Markdown."""
        if not self.findings:
            return "暂无可用信息"

        parts = ["## 任务总结\n"]
        for i, f in enumerate(self.findings, 1):
            parts.append(f"### {i}. {f.title}\n")
            if f.meaning:
                parts.append(f"- **含义与价值**：{f.meaning}\n")
            if f.expansion:
                parts.append(f"- **多维度拓展**：{f.expansion}\n")
            parts.append("")

        return "\n".join(parts).strip()


def normalize_summary(text: str) -> str:
    """Parse and reformat a task summary, falling back to raw text on failure."""
    parsed = TaskSummary.from_markdown(text)
    if parsed is not None and parsed.findings:
        return parsed.to_markdown()
    # If parsing failed but we have content, return as-is
    return text
