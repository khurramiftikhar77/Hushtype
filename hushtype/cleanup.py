"""Turns raw Whisper text into what gets pasted.

Steps, in order: snippets, spoken formatting commands, filler removal,
replacements, spacing and capitalisation. English-only steps are skipped for
Urdu.
"""

from __future__ import annotations

import re
import string

FILLERS = ["um", "umm", "uh", "uhh", "uhm", "erm", "er", "ah", "hmm", "mm", "mhm"]

_FILLER_RE = re.compile(r"\b(?:" + "|".join(FILLERS) + r")\b[,.]?\s*", flags=re.IGNORECASE)

# Spoken layout commands. Punctuation itself is added automatically by
# Whisper, so only line breaks (which it cannot guess) are voice commands.
# Whisper often wraps them in punctuation ("Thanks. New paragraph. See you"),
# so a trailing , or . is swallowed.
SPOKEN = [
    ("new paragraph", "\n\n"),
    ("new line", "\n"),
]
_SPOKEN_RES = [
    (re.compile(r"[ \t]*\b" + re.escape(phrase) + r"\b[,.!?]?[ \t]*", flags=re.IGNORECASE), out)
    for phrase, out in SPOKEN
]

_SPACE_BEFORE_PUNCT = re.compile(r"[ \t]+([,.!?;:])")
_DOUBLE_PUNCT = re.compile(r"([,.!?;:])[ \t]*,")
_REPEAT_PUNCT = re.compile(r"([.!?])[ \t]*[.]")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_LEADING_PUNCT = re.compile(r"^[\s,.;:]+")
_SPACE_AROUND_NL = re.compile(r"[ \t]*\n[ \t]*")
_COMMA_BEFORE_END = re.compile(r",([.!?])")


def _norm(text: str) -> str:
    return text.lower().strip().strip(string.punctuation + " ").strip()


def apply_snippets(text: str, snippets: dict[str, str]) -> str:
    if not snippets:
        return text
    # The whole dictation is a trigger: paste the snippet exactly.
    whole = _norm(text)
    for trigger, value in snippets.items():
        if whole == _norm(trigger):
            return value
    # Otherwise replace triggers inside the sentence.
    for trigger, value in sorted(snippets.items(), key=lambda kv: -len(kv[0])):
        t = _norm(trigger)
        if t:
            text = re.sub(r"\b" + re.escape(t) + r"\b[.]?", lambda _m: value, text, flags=re.IGNORECASE)
    return text


def apply_spoken_commands(text: str) -> str:
    for rx, out in _SPOKEN_RES:
        text = rx.sub(lambda _m, o=out: o if o in "\n\n" else o + " ", text)
    return text


def remove_fillers(text: str) -> str:
    return _FILLER_RE.sub("", text)


def apply_replacements(text: str, replacements: dict[str, str]) -> str:
    for wrong, right in replacements.items():
        pattern = re.compile(r"\b" + re.escape(wrong) + r"\b", flags=re.IGNORECASE)
        text = pattern.sub(lambda _m: right, text)
    return text


def _capitalize_sentences(text: str) -> str:
    return re.sub(r"(^|[.!?]\s+|\n\s*)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)


def clean(text: str, *, language: str = "en", fillers: bool = True, capitalize: bool = True,
          spoken_commands: bool = True, replacements: dict[str, str] | None = None,
          snippets: dict[str, str] | None = None) -> str:
    text = text.strip()
    if not text:
        return ""
    if snippets:
        before = text
        text = apply_snippets(text, snippets)
        if text != before and text in snippets.values():
            return text  # an exact snippet is pasted as written
    english = language == "en"
    if spoken_commands and english:
        text = apply_spoken_commands(text)
    if fillers and english:
        text = remove_fillers(text)
    if replacements:
        text = apply_replacements(text, replacements)
    text = _SPACE_AROUND_NL.sub("\n", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _DOUBLE_PUNCT.sub(r"\1", text)
    text = _REPEAT_PUNCT.sub(r"\1", text)
    text = _COMMA_BEFORE_END.sub(r"\1", text)
    text = _MULTI_SPACE.sub(" ", text)
    text = _LEADING_PUNCT.sub("", text)
    if capitalize and english:
        text = _capitalize_sentences(text)
    return text.strip(" \t")
