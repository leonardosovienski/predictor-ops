"""Deterministic, stdlib-only redaction before operational persistence."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import parse_qsl, urlsplit, urlunsplit

REDACTED = "[REDACTED]"
REDACTION_FAILED = "[REDACTION_FAILED]"
MIN_SECRET_LENGTH = 8
SENSITIVE_KEY = re.compile(r"(?i)(?:api[_-]?key|token|password|secret|authorization|auth|credential|access[_-]?key|private[_-]?key|client[_-]?secret)")
SENSITIVE_NAME_FRAGMENT = r"(?:api[_-]?key|token|password|secret|authorization|auth|credential|access[_-]?key|private[_-]?key|client[_-]?secret)"
ASSIGNMENT = re.compile(rf"(?P<key>[\"']?(?=[A-Za-z0-9_.-]*{SENSITIVE_NAME_FRAGMENT})[A-Za-z][A-Za-z0-9_.-]*[\"']?)\s*(?P<sep>=|:)\s*(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;}}&]+)", re.IGNORECASE)
BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
AUTH_HEADER = re.compile(r"(?im)^(?P<key>Authorization|Proxy-Authorization)\s*:\s*[^\r\n]+")
URL_CANDIDATE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)


def _as_text(value: str | bytes | object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value if isinstance(value, str) else str(value)


def collect_sensitive_values(environment: Mapping[str, str] | None = None, configuration: Mapping[str, Any] | None = None) -> tuple[str, ...]:
    """Return only sufficiently long values under explicitly sensitive names."""
    values: set[str] = set()
    for source in (os.environ if environment is None else environment, configuration or {}):
        for key, value in source.items():
            text = _as_text(value).strip()
            if SENSITIVE_KEY.search(str(key)) and len(text) >= MIN_SECRET_LENGTH:
                values.add(text)
    return tuple(sorted(values, key=len, reverse=True))


def _redact_url(match: re.Match[str]) -> str:
    candidate = match.group(0)
    trailing = ""
    while candidate and candidate[-1] in ".,;)]}":
        trailing = candidate[-1] + trailing
        candidate = candidate[:-1]
    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname or ""
        if not hostname:
            return match.group(0)
        netloc = hostname
        if parsed.port:
            netloc += f":{parsed.port}"
        if parsed.username is not None or parsed.password is not None:
            netloc = f"{REDACTED}@{netloc}"
        query = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            query.append(f"{key}={REDACTED if SENSITIVE_KEY.search(key) else value}")
        return urlunsplit((parsed.scheme, netloc, parsed.path, "&".join(query), parsed.fragment)) + trailing
    except (TypeError, ValueError):
        return match.group(0)


def redact_text(value: str | bytes | object, sensitive_values: Iterable[str] = ()) -> str:
    """Redact text without raising and without retaining secret fragments."""
    text = _as_text(value)
    for secret in sorted({item for item in sensitive_values if len(item) >= MIN_SECRET_LENGTH}, key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    text = AUTH_HEADER.sub(lambda match: f"{match.group('key')}: {REDACTED}", text)
    text = BEARER.sub(f"Bearer {REDACTED}", text)
    text = URL_CANDIDATE.sub(_redact_url, text)
    return ASSIGNMENT.sub(lambda match: f"{match.group('key')}{match.group('sep')}{REDACTED}", text)


def redact_mapping(value: Any, sensitive_values: Iterable[str] = ()) -> Any:
    if isinstance(value, Mapping):
        return {str(key): REDACTED if SENSITIVE_KEY.search(str(key)) else redact_mapping(item, sensitive_values) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_mapping(item, sensitive_values) for item in value]
    if isinstance(value, tuple):
        return [redact_mapping(item, sensitive_values) for item in value]
    if isinstance(value, (str, bytes)):
        return redact_text(value, sensitive_values)
    return value


def safe_redact_text(value: str | bytes | object, sensitive_values: Iterable[str] = ()) -> str:
    try:
        return redact_text(value, sensitive_values)
    except Exception:
        return REDACTION_FAILED


def safe_redact_mapping(value: Any, sensitive_values: Iterable[str] = ()) -> Any:
    try:
        return redact_mapping(value, sensitive_values)
    except Exception:
        return REDACTION_FAILED


def redact_command(command: Sequence[str], sensitive_values: Iterable[str] = ()) -> list[str]:
    redacted = [safe_redact_text(item, sensitive_values) for item in command]
    for index, item in enumerate(command[:-1]):
        normalized = item.lstrip("-")
        if SENSITIVE_KEY.search(normalized) and "=" not in item:
            redacted[index + 1] = REDACTED
    return redacted


def occurrence_kinds(value: str | bytes | object, sensitive_values: Iterable[str] = ()) -> dict[str, int]:
    text = _as_text(value)
    kinds: dict[str, int] = {}
    checks = {
        "known_value": sum(text.count(item) for item in sensitive_values if len(item) >= MIN_SECRET_LENGTH),
        "authorization_header": len(AUTH_HEADER.findall(text)),
        "bearer": len(BEARER.findall(text)),
        "sensitive_assignment": len(ASSIGNMENT.findall(text)),
        "sensitive_url": sum(1 for match in URL_CANDIDATE.finditer(text) if redact_text(match.group(0)) != match.group(0)),
    }
    return {kind: count for kind, count in checks.items() if count}


def scan_path(path: Path, sensitive_values: Iterable[str] = ()) -> dict[str, Any]:
    text = path.read_bytes()
    kinds = occurrence_kinds(text, sensitive_values)
    return {"path": str(path), "occurrence_count": redact_text(text, sensitive_values).count(REDACTED), "kinds": kinds}


def atomic_sanitize(source: Path, destination: Path, sensitive_values: Iterable[str] = ()) -> dict[str, Any]:
    original_stat = source.stat()
    sanitized = redact_text(source.read_bytes(), sensitive_values)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False, dir=destination.parent, prefix=f".{destination.name}.") as handle:
        handle.write(sanitized)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, destination)
    os.utime(destination, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    return scan_path(destination, sensitive_values)


def _paths(values: Sequence[str]) -> list[Path]:
    return [Path(value).resolve() for value in values]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely inventory or sanitize potential secret-bearing logs.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan = subparsers.add_parser("scan")
    scan.add_argument("paths", nargs="+")
    sanitize = subparsers.add_parser("sanitize")
    sanitize.add_argument("source")
    sanitize.add_argument("--output")
    sanitize.add_argument("--dry-run", action="store_true")
    sanitize.add_argument("--replace", action="store_true")
    sanitize.add_argument("--confirm-replace", action="store_true")
    args = parser.parse_args(argv)
    values = collect_sensitive_values(os.environ)
    try:
        if args.command == "scan":
            report = [scan_path(path, values) for path in _paths(args.paths)]
            print(json.dumps(report, sort_keys=True))
            return 0
        source = Path(args.source).resolve()
        before = scan_path(source, values)
        if args.dry_run:
            print(json.dumps({"dry_run": True, "source": before}, sort_keys=True))
            return 0
        if args.replace and not args.confirm_replace:
            print("refusing replacement without --confirm-replace", file=os.sys.stderr)
            return 2
        destination = source if args.replace else Path(args.output).resolve() if args.output else source.with_name(source.stem + ".sanitized" + source.suffix)
        after = atomic_sanitize(source, destination, values)
        print(json.dumps({"source": before, "sanitized": after, "replaced": args.replace}, sort_keys=True))
        return 0
    except (OSError, ValueError, UnicodeError) as exc:
        print(f"sanitization failed: {safe_redact_text(exc, values)}", file=os.sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
