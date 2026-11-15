"""Post-processing of raw Whisper text: fillers, replacements, spacing."""

from __future__ import annotations

import re

FILLERS = ["um", "umm", "uh", "uhh", "uhm", "erm", "er", "ah", "hmm", "mm", "mhm"]

# A filler as a whole word, plus an optional trailing comma it often carries.
_FILLER_RE = re.compile(
    r"\b(?:" + "|".join(FILLERS) + r")\b[,.]?\s*",
    flags=re.IGNORECASE,
)
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.!?;:])")
_DOUBLE_PUNCT = re.compile(r"([,.!?;:])\s*,")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_LEADING_PUNCT = re.compile(r"^[\s,.;:]+")


def remove_fillers(text: str) -> str:
    return _FILLER_RE.sub("", text)


def apply_replacements(text: str, replacements: dict[str, str]) -> str:
    for wrong, right in replacements.items():
        pattern = re.compile(r"\b" + re.escape(wrong) + r"\b", flags=re.IGNORECASE)
        text = pattern.sub(right, text)
    return text


def _capitalize_sentences(text: str) -> str:
    def up(m: re.Match) -> str:
        return m.group(1) + m.group(2).upper()

    text = re.sub(r"(^|[.!?]\s+)([a-z])", up, text)
    return text


def clean(text: str, *, fillers: bool = True, replacements: dict[str, str] | None = None) -> str:
    text = text.strip()
    if fillers:
        text = remove_fillers(text)
    if replacements:
        text = apply_replacements(text, replacements)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _DOUBLE_PUNCT.sub(r"\1", text)
    text = _MULTI_SPACE.sub(" ", text)
    text = _LEADING_PUNCT.sub("", text)
    text = _capitalize_sentences(text)
    return text.strip()
