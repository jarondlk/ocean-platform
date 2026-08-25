"""Helpers for safely embedding untrusted text into model prompts."""
from __future__ import annotations

from html import escape


MAX_PROMPT_FIELD_CHARS = 8000
MAX_PROMPT_SECTION_CHARS = 32000


def safe_prompt_text(value: object, *, max_chars: int = MAX_PROMPT_FIELD_CHARS) -> str:
    """Escape prompt delimiters and bound untrusted text before interpolation."""
    text = "" if value is None else str(value)
    if len(text) > max_chars:
        text = f"{text[:max_chars]}\n[content truncated]"
    return escape(text, quote=False)


def bound_prompt_section(section: str, *, max_chars: int = MAX_PROMPT_SECTION_CHARS) -> str:
    """Keep one evidence/context section within a predictable prompt budget."""
    if len(section) <= max_chars:
        return section
    return f"{section[:max_chars]}\n[section truncated]"
