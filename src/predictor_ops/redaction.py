from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"
# Floor for values auto-harvested from the environment by sensitive_values().
# Below this length, a short/generic value (a placeholder, a test fixture) is
# too likely to coincidentally appear as a substring of unrelated generated
# data (a run_id, a timestamp) — redact_text()/redact() would then corrupt
# that unrelated field via blind substring replacement. This floor only
# gates automatic environment harvesting; a caller that explicitly passes a
# short secret to redact()/redact_text()/redact_command() still gets it
# redacted, since that's a deliberate, scoped instruction rather than a
# blanket sweep of every "sensitive-named" env var in the process.
MIN_SENSITIVE_VALUE_LENGTH = 12
SENSITIVE_KEY = re.compile(r"(?i)(?:secret|token|password|passwd|api[_-]?key|authorization|credential|private[_-]?key)")
ASSIGNMENT = re.compile(
    r"(?i)(?P<key>(?:secret|token|password|passwd|api[_-]?key|authorization|credential))(?P<sep>\s*[:=]\s*)(?P<value>[^\s,;&]+)"
)
BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
URL_SECRET = re.compile(
    r"(?i)(?P<prefix>[?&](?:secret|token|password|passwd|api[_-]?key|authorization|credential)=)[^&#\s]*"
)
SENSITIVE_FLAG = re.compile(
    r"(?i)^--?(?:secret|token|password|passwd|api[_-]?key|authorization|proxy-authorization|credential)$"
)


def sensitive_values(environment: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                value
                for key, value in environment.items()
                if value and len(value) >= MIN_SENSITIVE_VALUE_LENGTH and SENSITIVE_KEY.search(key)
            },
            key=len,
            reverse=True,
        )
    )


def redact_text(value: object, secrets: Sequence[str] = ()) -> str:
    try:
        text = str(value)
        for secret in sorted({item for item in secrets if item}, key=len, reverse=True):
            text = text.replace(secret, REDACTED)
        text = BEARER.sub(f"Bearer {REDACTED}", text)
        text = URL_SECRET.sub(lambda match: match.group("prefix") + REDACTED, text)
        return ASSIGNMENT.sub(lambda match: f"{match.group('key')}{match.group('sep')}{REDACTED}", text)
    except Exception:
        return "[REDACTION_FAILED]"


def redact(value: Any, secrets: Sequence[str] = ()) -> Any:
    if isinstance(value, Mapping):
        return {
            redact_text(key, secrets): REDACTED if SENSITIVE_KEY.search(str(key)) else redact(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item, secrets) for item in value]
    if isinstance(value, str):
        return redact_text(value, secrets)
    return value


def redact_command(command: Sequence[str], secrets: Sequence[str] = ()) -> list[str]:
    output: list[str] = []
    redact_next = False
    for part in command:
        if redact_next:
            output.append(REDACTED)
            redact_next = False
            continue
        output.append(redact_text(part, secrets))
        redact_next = bool(SENSITIVE_FLAG.fullmatch(part))
    return output
