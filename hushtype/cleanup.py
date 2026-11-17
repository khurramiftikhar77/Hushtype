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


# ---------- self-correction ----------

_CORRECTION = re.compile(
    r"[,.;]?\s*\b(?:no,?\s+wait|sorry,?\s+i\s+mean|no,?\s+i\s+mean|i\s+meant|or\s+rather)\b[,.;:]?\s*",
    re.IGNORECASE)
_SCRATCH = re.compile(r"\s*\bscratch\s+that\b[,.!]?\s*", re.IGNORECASE)
_CLAUSE_END = re.compile(r"[,.!?;\n]")


def apply_self_corrections(text: str) -> str:
    """'Meet on Monday, no wait, Tuesday' -> 'Meet on Tuesday'. English only."""
    # "scratch that" removes the sentence before it.
    while (m := _SCRATCH.search(text)):
        before = text[: m.start()]
        cut = max(before.rfind(". ", 0, len(before) - 1), before.rfind("! ", 0, len(before) - 1),
                  before.rfind("? ", 0, len(before) - 1), before.rfind("\n", 0, len(before) - 1))
        keep = before[: cut + 2] if cut >= 0 else ""
        text = keep + text[m.end():]
    # "X, no wait, Y": Y replaces as many words before the marker as Y has.
    for _ in range(5):
        m = _CORRECTION.search(text)
        if not m:
            break
        before, after = text[: m.start()], text[m.end():]
        end = _CLAUSE_END.search(after)
        fix = after[: end.start()] if end else after
        rest = after[len(fix):]
        fix_words = fix.split()
        if not fix_words:
            text = before + rest
            continue
        clause_start = max(before.rfind(c) for c in ",.!?;\n") + 1
        head, clause = before[:clause_start], before[clause_start:]
        words = clause.split()
        n = min(len(fix_words), len(words))
        kept = words[: len(words) - n]
        lead = " " if head and not head.endswith((" ", "\n")) else ""
        text = head + lead + " ".join(kept + fix_words) + rest
    return text


# ---------- smart formatting ----------

_ORDINALS = [("first", "firstly"), ("second", "secondly"), ("third", "thirdly"), ("fourth", "fourthly"),
             ("fifth", "fifthly"), ("sixth",), ("seventh",)]
_ORDINAL_WORDS = {w: i for i, group in enumerate(_ORDINALS) for w in group}
_LIST_ITEM = re.compile(r"(?:^|(?<=[.!?:]\s)|(?<=\n))(first(?:ly)?|second(?:ly)?|third(?:ly)?|fourth(?:ly)?|fifth(?:ly)?|"
                        r"sixth|seventh|finally|lastly)\b[,:]?\s*", re.IGNORECASE)


def format_lists(text: str) -> str:
    """'First, ... Second, ... Finally, ...' -> a numbered list."""
    marks = list(_LIST_ITEM.finditer(text))
    words = [m.group(1).lower() for m in marks]
    if "first" not in words and "firstly" not in words:
        return text
    if sum(w not in ("finally", "lastly") for w in words) < 2:
        return text
    start = next(i for i, w in enumerate(words) if w in ("first", "firstly"))
    marks = marks[start:]
    intro = text[: marks[0].start()].rstrip()
    lines = [intro] if intro else []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        item = text[m.end():end].strip()
        if item:
            lines.append(f"{i + 1}. {item[0].upper()}{item[1:]}")
    return "\n".join(lines)


_GREETING = re.compile(r"^((?:hi|hello|hey|dear|good\s+(?:morning|afternoon|evening))\b[^,.!?\n]{0,40}[,!])\s*",
                       re.IGNORECASE)
_SIGNOFF = re.compile(r"[.!]?\s*\b((?i:best\s+regards|kind\s+regards|warm\s+regards|regards|many\s+thanks|"
                      r"thanks\s+(?:a\s+lot|again)|thank\s+you|thanks|cheers|best|sincerely|yours\s+sincerely))"
                      r"[,.!]?\s*([A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)?)?[.!]?\s*$")


def format_email(text: str) -> str:
    """Greeting on its own line, sign-off and name at the bottom."""
    g = _GREETING.match(text)
    if g and len(text) > len(g.group(0)) + 10:
        text = g.group(1) + "\n\n" + text[g.end():]
    m = _SIGNOFF.search(text)
    if m and m.start() > len(text) * 0.4:
        body = text[: m.start()].rstrip()
        closing = m.group(1)
        closing = closing[0].upper() + closing[1:]
        name = m.group(2)
        if not body.endswith((".", "!", "?")):
            body += "."
        text = f"{body}\n\n{closing},\n{name}" if name else f"{body}\n\n{closing},"
    return text


# Punjabi is heard with the Urdu model, which tends to write Urdu helper words
# for spoken Punjabi ones ("ہے" for "اے"). Only words that never mean something
# else in Punjabi are swapped.
PUNJABI_WORDS = {"ہے": "اے", "ہیں": "نیں", "بھی": "وی", "تھا": "سی", "تھی": "سی", "تھے": "سن",
                 "تھیں": "سن", "کیوں کہ": "کیونکہ"}
_PUNJABI_RE = re.compile(r"(?<!\w)(" + "|".join(sorted(map(re.escape, PUNJABI_WORDS), key=len, reverse=True)) + r")(?!\w)")


def punjabi_words(text: str) -> str:
    return _PUNJABI_RE.sub(lambda m: PUNJABI_WORDS[m.group(1)], text)


def clean(text: str, *, language: str = "en", fillers: bool = True, capitalize: bool = True,
          spoken_commands: bool = True, replacements: dict[str, str] | None = None,
          snippets: dict[str, str] | None = None, self_correct: bool = True,
          lists: bool = True, email: bool = False) -> str:
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
    if self_correct and english:
        text = apply_self_corrections(text)
    if language == "pa":
        text = punjabi_words(text)
    if replacements:
        text = apply_replacements(text, replacements)
    text = _SPACE_AROUND_NL.sub("\n", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _DOUBLE_PUNCT.sub(r"\1", text)
    text = _REPEAT_PUNCT.sub(r"\1", text)
    text = _COMMA_BEFORE_END.sub(r"\1", text)
    text = _MULTI_SPACE.sub(" ", text)
    text = _LEADING_PUNCT.sub("", text)
    if lists and english:
        text = format_lists(text)
    if email and english:
        text = format_email(text)
    if capitalize and english:
        text = _capitalize_sentences(text)
    return text.strip(" \t")
