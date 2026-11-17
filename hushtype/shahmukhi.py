"""Gurmukhi to Shahmukhi: writes Punjabi heard by Whisper in Gurmukhi in the Urdu-style script.

Whisper recognises spoken Punjabi much better when it listens *as Punjabi*, but it
can only write Punjabi in Gurmukhi (the script used in India). Pakistani Punjabi is
written in Shahmukhi, so the text is converted letter by letter. Short vowels are
dropped, as Shahmukhi normally does, and common words get their usual spelling.
"""
from __future__ import annotations

import re

CONSONANTS = {
    "ਕ": "ک", "ਖ": "کھ", "ਗ": "گ", "ਘ": "گھ", "ਙ": "ن", "ਚ": "چ", "ਛ": "چھ", "ਜ": "ج", "ਝ": "جھ", "ਞ": "ن",
    "ਟ": "ٹ", "ਠ": "ٹھ", "ਡ": "ڈ", "ਢ": "ڈھ", "ਣ": "ن", "ਤ": "ت", "ਥ": "تھ", "ਦ": "د", "ਧ": "دھ", "ਨ": "ن",
    "ਪ": "پ", "ਫ": "پھ", "ਬ": "ب", "ਭ": "بھ", "ਮ": "م", "ਯ": "ی", "ਰ": "ر", "ਲ": "ل", "ਵ": "و", "ੜ": "ڑ",
    "ਸ": "س", "ਹ": "ہ", "ਸ਼": "ش", "ਖ਼": "خ", "ਗ਼": "غ", "ਜ਼": "ز", "ਫ਼": "ف", "ਲ਼": "ل",
}
# Precomposed letters with a dot (nukta), as Whisper usually writes them.
CONSONANTS.update({"\u0a36": "ش", "\u0a59": "خ", "\u0a5a": "غ", "\u0a5b": "ز", "\u0a5e": "ف", "\u0a33": "ل"})
NUKTA_FORMS = {"ਸ": "ش", "ਖ": "خ", "ਗ": "غ", "ਜ": "ز", "ਫ": "ف", "ਕ": "ق", "ਲ": "ل"}
# Independent vowels: at the start of a word, and after another vowel.
INITIAL = {"ਅ": "ا", "ਆ": "آ", "ਇ": "ا", "ਈ": "ای", "ਉ": "ا", "ਊ": "او", "ਏ": "اے", "ਐ": "اے", "ਓ": "او", "ਔ": "او"}
MEDIAL = {"ਅ": "ا", "ਆ": "ا", "ਇ": "ی", "ਈ": "ئی", "ਉ": "و", "ਊ": "و", "ਏ": "ئے", "ਐ": "ئے", "ਓ": "و", "ਔ": "و"}
SIGNS = {"ਾ": "ا", "ਿ": "", "ੀ": "ی", "ੁ": "", "ੂ": "و", "ੇ": "ی", "ੈ": "ی", "ੋ": "و", "ੌ": "و"}
NASALS = ("ਂ", "ੰ")
ADDAK, VIRAMA, NUKTA = "ੱ", "੍", "਼"
PUNCT = {"।": "۔", "॥": "۔", ",": "،", "?": "؟", ";": "؛"}
DIGITS = {chr(0x0A66 + i): str(i) for i in range(10)}

# Usual Shahmukhi spelling for frequent words, where letter-by-letter differs
# (Persian/Arabic loanwords, and words Shahmukhi writes with a silent letter).
WORDS = {
    "ਇਹ": "ایہہ", "ਉਹ": "اوہ", "ਇਸ": "اس", "ਉਸ": "اوس", "ਇੱਥੇ": "ایتھے", "ਉੱਥੇ": "اوتھے", "ਕਿੱਥੇ": "کتھے",
    "ਹੈ": "اے", "ਹਨ": "نیں", "ਹਾਂ": "آں", "ਸੀ": "سی", "ਨੇ": "نے", "ਤੇ": "تے", "ਦੇ": "دے", "ਕਿ": "کہ",
    "ਮੈਂ": "میں", "ਮੈਨੂੰ": "مینوں", "ਤੈਨੂੰ": "تینوں", "ਸਾਨੂੰ": "سانوں", "ਤੁਹਾਨੂੰ": "تہانوں", "ਤੁਸੀਂ": "تسی",
    "ਕੀ": "کی", "ਕਿਉਂ": "کیوں", "ਕਿਵੇਂ": "کیویں", "ਕਦੋਂ": "کدوں", "ਨਹੀਂ": "نہیں", "ਵੀ": "وی", "ਜੀ": "جی",
    "ਹਾਲ": "حال", "ਸ਼ੁਕਰੀਆ": "شکریہ", "ਸ਼ੁਕਰਿਆ": "شکریہ", "ਸਲਾਮ": "سلام", "ਅੱਲ੍ਹਾ": "اللہ", "ਅੱਲਾ": "اللہ",
    "ਖ਼ੁਦਾ": "خدا", "ਸਾਹਿਬ": "صاحب", "ਵਕਤ": "وقت", "ਸਬਰ": "صبر", "ਸਾਫ਼": "صاف", "ਜ਼ਰੂਰ": "ضرور",
    "ਮਾਫ਼": "معاف", "ਮਾਫ਼ੀ": "معافی", "ਖ਼ਬਰ": "خبر", "ਦੁਨੀਆ": "دنیا", "ਪਾਕਿਸਤਾਨ": "پاکستان", "ਲਾਹੌਰ": "لاہور",
    "ਮਸਲਾ": "مسئلہ", "ਸਵਾਲ": "سوال", "ਜਵਾਬ": "جواب", "ਇਲਾਵਾ": "علاوہ", "ਤਰ੍ਹਾਂ": "طرح", "ਤਰਾਂ": "طرح",
    "ਸ਼ਹਿਰ": "شہر", "ਕੰਮ": "کم", "ਗੱਲ": "گل", "ਕੱਲ੍ਹ": "کل", "ਅੱਜ": "اج", "ਹੁਣ": "ہن", "ਬਹੁਤ": "بہت",
    "ਪਤਾ": "پتہ", "ਸੁਣਾਓ": "سناؤ", "ਆਓ": "آؤ", "ਜਾਓ": "جاؤ", "ਫੇਰ": "فیر", "ਫਿਰ": "فیر", "ਯਾਰ": "یار", "ਭਰਾ": "پرا", "ਵੱਲ": "ول", "ਇਕ": "اک", "ਇੱਕ": "اک", "ਦੋ": "دو",
}

_WORD = re.compile(r"[਀-੿]+")


def _word(w: str) -> str:
    if w in WORDS:
        return WORDS[w]
    out: list[str] = []
    i, n = 0, len(w)
    while i < n:
        ch = w[i]
        nxt = w[i + 1] if i + 1 < n else ""
        if ch in CONSONANTS:
            letter = CONSONANTS[ch]
            if nxt == NUKTA:
                letter = NUKTA_FORMS.get(ch, letter)
                i += 1
            nxt = w[i + 1] if i + 1 < n else ""
            if nxt == VIRAMA and i + 2 < n:
                sub = w[i + 2]
                # Subjoined letters: ਹ adds breath (ھ), ਰ and ਵ are written in full.
                letter += {"ਹ": "ھ", "ਰ": "ر", "ਵ": "و"}.get(sub, CONSONANTS.get(sub, ""))
                i += 2
            out.append(letter)
        elif ch in SIGNS:
            sign = SIGNS[ch]
            if ch in ("ੇ", "ੈ") and i + 1 >= n:
                sign = "ے"  # final e / ai: bari ye
            if ch == "ਿ" and nxt in INITIAL:
                sign = "ی"  # ਕਿਉਂ -> کیوں
            out.append(sign)
        elif ch in INITIAL:
            out.append(INITIAL[ch] if not out else MEDIAL[ch])
        elif ch in NASALS:
            at_end = i + 1 >= n
            out.append("ں" if at_end else ("م" if nxt in ("ਬ", "ਪ", "ਭ", "ਮ") else "ن"))
        elif ch in (ADDAK, VIRAMA, NUKTA, "ੑ", "ੵ", "ੳ", "ੲ"):
            pass  # doubling and marks: Shahmukhi leaves them out
        elif ch in DIGITS:
            out.append(DIGITS[ch])
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def to_shahmukhi(text: str) -> str:
    """Converts any Gurmukhi words in text to Shahmukhi; other text is left alone."""
    if not _WORD.search(text):
        return text
    text = _WORD.sub(lambda m: _word(m.group(0)), text)
    for g, s in {**PUNCT, **DIGITS}.items():
        text = text.replace(g, s)
    return re.sub(r"\s+([،۔؟؛])", r"\1", text)
