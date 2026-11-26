"""Provenance filter: keep only text the sender visibly authored.

Hidden HTML, quoted/forwarded threads and attachment text can carry data,
but must never drive actions. Deterministic, runs before any LLM.
"""
import html
import re

# ponytail: regex over flattened text; production should split real MIME parts
# (text/plain body vs attachments) and use an HTML sanitizer, not regex.
_HIDDEN_STYLE = r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|color\s*:\s*#fff(?:fff)?\b|color\s*:\s*white"
_HIDDEN_EL = re.compile(
    rf"<(\w+)[^>]*style\s*=\s*['\"][^'\"]*(?:{_HIDDEN_STYLE})[^'\"]*['\"][^>]*>.*?</\1\s*>",
    re.I | re.S,
)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_TAG = re.compile(r"<[^>]+>")
_CUT_MARKERS = re.compile(
    r"^\s*(?:-+\s*Forwarded message\s*-+|-+\s*Original Message\s*-+|\[attachment\b|On .+ wrote:\s*$)",
    re.I | re.M,
)


def authored_text(email: str) -> str:
    text = _COMMENT.sub("", email)
    text = _HIDDEN_EL.sub("", text)
    text = html.unescape(_TAG.sub(" ", text))
    m = _CUT_MARKERS.search(text)
    if m:
        text = text[: m.start()]
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith(">")]
    return re.sub(r"[ \t]+", " ", "\n".join(lines)).strip()
