"""Learning from the user: corrections made in History, and names used often.

Only clear fixes are learned (misspellings, names, capitalisation), never
rewording, so Hushtype does not start changing ordinary words.
"""

from __future__ import annotations

import difflib
import re

_WORD = re.compile(r"[\w'’-]+")
# Words too common to ever be rewritten automatically.
_COMMON = set("""
a an the is are was were be been am i you he she it we they me him her us them my your his its our their
to of and or but in on at for with from by as that this these those not no yes do did does done have has had
so if then than there here what which who when where why how all any some can could will would should
""".split())
_SENTENCE_START = re.compile(r"(?:^|[.!?\n]\s*)$")


def _similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(a=a.lower(), b=b.lower()).ratio()


def _looks_like_fix(wrong: str, right: str) -> bool:
    if not wrong or not right or wrong.lower() in _COMMON:
        return False
    if len(wrong) < 3 and len(right) < 3:
        return False
    if _similar(wrong, right) >= 0.5:  # a misspelling or misheard variant
        return True
    # A name or acronym replacing a misheard word, e.g. "eye" -> "AI".
    return right[:1].isupper() and right.lower() not in _COMMON


def extract_corrections(old: str, new: str, max_words: int = 3) -> list[tuple[str, str]]:
    """Word-level fixes between what Hushtype wrote and what the user saved."""
    a, b = _WORD.findall(old), _WORD.findall(new)
    sm = difflib.SequenceMatcher(a=[w.lower() for w in a], b=[w.lower() for w in b], autojunk=False)
    found: list[tuple[str, str]] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "replace" and 1 <= i2 - i1 <= max_words and 1 <= j2 - j1 <= max_words:
            wrong, right = " ".join(a[i1:i2]), " ".join(b[j1:j2])
            if _looks_like_fix(wrong, right):
                found.append((wrong, right))
        elif op == "equal":
            for k in range(i2 - i1):  # capitalisation fixes of names: "khurram" -> "Khurram"
                w, r = a[i1 + k], b[j1 + k]
                if w != r and r[:1].isupper() and w.lower() not in _COMMON and len(w) >= 3:
                    found.append((w, r))
    out, seen = [], set()
    for w, r in found:
        if w.lower() not in seen:
            seen.add(w.lower())
            out.append((w.lower(), r))
    return out


def candidate_names(text: str) -> list[str]:
    """Capitalised words in the middle of a sentence: names, brands, places."""
    names = []
    for m in _WORD.finditer(text):
        word = m.group(0)
        if len(word) < 3 or not word[:1].isupper() or word.lower() in _COMMON:
            continue
        if _SENTENCE_START.search(text[: m.start()]):
            continue  # every sentence starts with a capital
        if word.isupper() and len(word) > 5:
            continue  # shouting, not a name
        names.append(word)
    return list(dict.fromkeys(names))
