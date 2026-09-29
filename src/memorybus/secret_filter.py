"""Secret detection run before anything is written to the store (PRD §16)."""

from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("github_token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{20,}")),
    (
        "credential_assignment",
        re.compile(
            r"(?i)(\b(password|passwd|pwd|api[_-]?key|secret|access[_-]?token|refresh[_-]?token"
            r"|session[_-]?token|cookie|cvv)|密码|口令|密钥|验证码)\s*[:=：是为]\s*\S{4,}"
        ),
    ),
    (
        "recovery_phrase",
        re.compile(r"(?i)\b(seed|recovery|mnemonic)\s+(phrase|words)\b|助记词"),
    ),
    ("verification_code", re.compile(r"(?i)(verification|otp|2fa)\s*code\D{0,10}\d{4,8}")),
]

_CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _luhn_ok(number: str) -> bool:
    digits = [int(d) for d in number if d.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def find_secrets(text: str) -> list[str]:
    """Return the kinds of secrets found in ``text`` (empty list means safe)."""
    found = [kind for kind, pattern in _PATTERNS if pattern.search(text)]
    if any(_luhn_ok(m.group()) for m in _CARD_CANDIDATE.finditer(text)):
        found.append("credit_card")
    return found
