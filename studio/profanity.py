"""The swear filter: hides swear words in clips, so a clip does not lose reach on YouTube Shorts, Reels or TikTok.

Three settings, per video and per creator:
  off    nothing is changed
  text   swear words are masked in the captions, the heading, the title, the description and the hashtags:
         the first letter stays and the rest become stars ("fucking" becomes "f******")
  bleep  the same, and in the sound each swear word is replaced by a beep

A word counts when it is one of the words below, or starts with one of the stems (so "fucking", "shitty" and
"motherfuckers" are caught). Stretched spellings ("fuuuck", "shiiit") are caught too. Words that only contain a
stem in the middle ("scunthorpe", "class", "assassin") are not touched. English, plus the common Hindi and Urdu
ones as people type them in Roman letters, since clips are often in Hinglish.
"""
from __future__ import annotations

import re

MODES = {"off": "Keep as spoken", "text": "Hide in text", "bleep": "Hide and bleep"}

# a word that starts with one of these is a swear word: fuck, fucking, fucker, fuckers, fucked...
STEMS = (
    "fuck", "motherfuck", "fck", "fuk", "shit", "bullshit", "horseshit", "bitch", "cunt", "asshole", "arsehole",
    "dickhead", "bastard", "pussy", "pussies", "whore", "slut", "wank", "twat", "cocksuck", "nigg", "faggot",
    "retard",
    # Hindi and Urdu, in Roman letters
    "madarchod", "maderchod", "madarjaat", "behenchod", "bhenchod", "behnchod", "benchod", "bhosd", "bhosad",
    "chutiy", "chutiya", "chodu", "chod", "gaand", "gandu", "lund", "lauda", "lavda", "lawda", "loda", "randi",
    "harami", "haramkhor", "kamina", "kutti", "jhaat", "jhant", "tatti",
)
# whole words only (as a stem they would catch harmless words: "ass" in "assist", "bc" in "bcz", "mc" in "mcdonalds")
WORDS = {
    "ass", "asses", "arse", "dick", "dicks", "cock", "cocks", "damnit", "goddamn", "goddamnit", "wtf", "stfu",
    "mf", "mfs", "bc", "mc", "bsdk", "bkl", "mkc", "lodu", "chut",
}
# never caught, though they start like a stem
SAFE = {"shitake", "shiitake", "dickens", "cockpit", "cockroach", "cocktail", "cocktails", "cockatoo", "chodna",
        "pussycat", "pussycats", "fukuoka", "fukushima", "niggle", "niggles", "niggling", "retardant", "retardants"}

_LETTERS = re.compile(r"[a-z]+")


def _squash(word: str) -> str:
    """Letters only, lower case, with a letter repeated three or more times shortened to one: fuuuck is fuck."""
    w = "".join(_LETTERS.findall(word.lower()))
    return re.sub(r"(.)\1{2,}", r"\1", w)


def is_swear(word: str) -> bool:
    w = _squash(word)
    if not w or w in SAFE:
        return False
    if w in WORDS:
        return True
    if any(w.startswith(s) for s in STEMS):
        return True
    # "shiit", "fuuck": a doubled letter shortened to one, then looked at again
    w2 = re.sub(r"(.)\1+", r"\1", w)
    return w2 != w and (w2 in WORDS or any(w2.startswith(s) for s in STEMS))


def mask_word(word: str) -> str:
    """The word with every letter after the first replaced by a star, keeping any punctuation round it."""
    m = re.match(r"^(\W*)(\w)(\w*)(\W*)$", word, re.UNICODE)
    if not m:
        return word
    lead, first, rest, tail = m.groups()
    return f"{lead}{first}{'*' * len(rest)}{tail}"


def clean_text(text: str) -> str:
    """The text with every swear word masked."""
    if not text:
        return text
    return re.sub(r"[\w'*]+", lambda m: mask_word(m.group(0)) if is_swear(m.group(0)) else m.group(0), str(text))


def clean_tags(tags) -> list:
    """Hashtags without the swear ones: a masked hashtag is no use to anyone."""
    return [t for t in (tags or []) if not is_swear(str(t).lstrip("#"))]


def clean_clip_text(clip: dict) -> dict:
    """Masks the words people read on and under a clip: its heading, title, description and hashtags."""
    for k in ("hook", "title", "description"):
        if clip.get(k):
            clip[k] = clean_text(clip[k])
    if clip.get("hashtags"):
        clip["hashtags"] = clean_tags(clip["hashtags"])
    if clip.get("highlight_words"):
        clip["highlight_words"] = [w for w in clip["highlight_words"] if not is_swear(str(w))]
    return clip


def clean_words(words: list) -> list:
    """Caption words (dicts with "w"), each swear word masked; the timings stay as they were."""
    return [dict(w, w=mask_word(w["w"])) if is_swear(w.get("w", "")) else w for w in words]


def bleeps(words: list, start: float, end: float, pad: float = 0.04) -> list:
    """Where to beep, in seconds from the start of the clip: [(from, to)], overlapping ones joined."""
    spans = []
    for w in words:
        if not is_swear(w.get("w", "")):
            continue
        a, b = max(start, float(w["s"]) - pad), min(end, float(w["e"]) + pad)
        if b - a >= 0.05:
            spans.append([a - start, b - start])
    spans.sort()
    out = []
    for a, b in spans:
        if out and a <= out[-1][1] + 0.02:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(round(a, 3), round(b, 3)) for a, b in out]
