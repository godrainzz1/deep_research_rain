"""Skill plugin system — YAML frontmatter + Markdown body, hot-reloadable."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SkillDefinition:
    """A parsed skill with its frontmatter metadata and Markdown body."""

    name: str
    version: str = "1.0"
    description: str = ""
    triggers: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    pipeline: str = "standard"          # quick | standard | deep
    output_format: str = "markdown"
    output_sections: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    body: str = ""                      # Markdown content below the frontmatter
    file_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "triggers": self.triggers,
            "tools": self.tools,
            "pipeline": self.pipeline,
            "output_format": self.output_format,
            "output_sections": self.output_sections,
            "constraints": self.constraints,
            "file_path": self.file_path,
        }


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_YAML_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def parse_skill_file(file_path: Path) -> SkillDefinition | None:
    """Parse a ``.skill.md`` file into a SkillDefinition.

    Returns None if the frontmatter is missing or invalid.
    """
    try:
        raw = file_path.read_text(encoding="utf-8")
    except Exception:
        logger.exception("Failed to read skill file: %s", file_path)
        return None

    m = _YAML_FRONTMATTER_RE.match(raw)
    if not m:
        logger.warning("Skill file missing YAML frontmatter: %s", file_path)
        return None

    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        logger.exception("Invalid YAML frontmatter in %s", file_path)
        return None

    name = meta.get("name") or file_path.stem.replace(".skill", "")
    body = raw[m.end():].strip()

    return SkillDefinition(
        name=name,
        version=str(meta.get("version", "1.0")),
        description=str(meta.get("description", "")),
        triggers=_as_str_list(meta.get("triggers")),
        tools=_as_str_list(meta.get("tools")),
        pipeline=str(meta.get("pipeline", "standard")),
        output_format=str(meta.get("output", {}).get("format", "markdown") if isinstance(meta.get("output"), dict) else "markdown"),
        output_sections=_as_str_list(meta.get("output", {}).get("sections", []) if isinstance(meta.get("output"), dict) else []),
        constraints=meta.get("constraints") if isinstance(meta.get("constraints"), dict) else {},
        body=body,
        file_path=str(file_path),
    )


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class SkillRegistry:
    """In-memory registry keyed by skill name with trigger-based lookup."""

    def __init__(self) -> None:
        self._by_name: dict[str, SkillDefinition] = {}
        self._by_trigger: dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition) -> None:
        self._by_name[skill.name] = skill
        for trigger in skill.triggers:
            self._by_trigger[trigger.lower()] = skill

    def clear(self) -> None:
        self._by_name.clear()
        self._by_trigger.clear()

    def get(self, name: str) -> SkillDefinition | None:
        return self._by_name.get(name)

    def find_by_trigger(self, user_input: str) -> SkillDefinition | None:
        """Return the first skill whose trigger keywords all appear in *user_input*.

        - Space-separated triggers (e.g. "code review"): each word must appear.
        - CJK triggers without spaces (e.g. "代码审查"): every character must appear
          somewhere in the input (order-independent).
        """
        lower = user_input.lower()
        ordered = sorted(self._by_trigger.items(), key=lambda kv: -len(kv[0]))
        for trigger, skill in ordered:
            t = trigger.lower()
            if " " in t:
                if all(w in lower for w in t.split()):
                    return skill
            else:
                if all(ch in lower for ch in t):
                    return skill
        return None

    def list_all(self) -> list[SkillDefinition]:
        return list(self._by_name.values())

    @property
    def count(self) -> int:
        return len(self._by_name)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class SkillEngine:
    """Loads skills from a directory and serves them via a registry."""

    def __init__(self, skills_dir: str | Path = "skills") -> None:
        self._dir = Path(skills_dir)
        self.registry = SkillRegistry()

    def load_all(self) -> int:
        """Scan the skills directory and (re)load every ``.skill.md`` file."""
        self.registry.clear()
        if not self._dir.exists():
            logger.warning("Skills directory not found: %s", self._dir)
            return 0

        count = 0
        for path in self._dir.glob("*.skill.md"):
            skill = parse_skill_file(path)
            if skill is not None:
                self.registry.register(skill)
                count += 1
                logger.info("Loaded skill: %s (%s)", skill.name, path.name)
        logger.info("SkillEngine loaded %d skill(s) from %s", count, self._dir)
        return count

    def reload(self) -> int:
        """Hot-reload: clear and re-scan the directory."""
        logger.info("SkillEngine hot-reload triggered")
        return self.load_all()

    def match(self, user_input: str) -> SkillDefinition | None:
        """Find a skill matching *user_input* by trigger keywords.

        Returns the first match, or the 'deep-research' default if nothing matches.
        """
        matched = self.registry.find_by_trigger(user_input)
        if matched is not None:
            return matched
        return self.registry.get("deep-research")
