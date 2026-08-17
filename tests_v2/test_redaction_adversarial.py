import json
import time
import uuid

import predictor_ops.redaction as redaction
from predictor_ops.redaction import (
    MIN_SENSITIVE_VALUE_LENGTH,
    REDACTED,
    redact,
    redact_command,
    redact_text,
    sensitive_values,
)


def test_flags_urls_headers_json_unicode_overlap_and_short_values():
    secrets = ("long-secret-value", "secret-value", "xy")
    command = ["tool", "--api-key", "long-secret-value", "--token=secret-value", "https://x.invalid/?password=xy"]
    rendered = json.dumps(redact_command(command, secrets))
    assert not any(secret in rendered for secret in secrets)
    assert redact_text("Authorization: Bearer long-secret-value", secrets).count(REDACTED) >= 1
    assert "segredo-🔐" not in redact_text("token=segredo-🔐", ("segredo-🔐",))
    assert redact({"outer": [{"Proxy-Authorization": "value"}]})["outer"][0]["Proxy-Authorization"] == REDACTED
    assert "xy" not in json.dumps(redact({"xy": "safe"}, secrets))


def test_invalid_bytes_idempotence_and_adversarial_runtime():
    first = redact_text(b"token=\xff")
    assert "token=" in first and REDACTED in first
    assert redact_text(redact_text("token=value")) == redact_text("token=value")
    started = time.monotonic()
    result = redact_text("a" * 500_000 + " token=value")
    assert time.monotonic() - started < 1.5 and result.endswith(REDACTED)


def test_internal_redactor_failure_is_fail_closed(monkeypatch):
    class Broken:
        def sub(self, *args, **kwargs):
            raise RuntimeError("broken")

    monkeypatch.setattr(redaction, "BEARER", Broken())
    assert redact_text("fixture-secret", ("fixture-secret",)) == "[REDACTION_FAILED]"


def test_short_sensitive_named_env_value_does_not_corrupt_unrelated_generated_data():
    """Regression test for a real corruption found during an ecosystem audit.

    run_job() harvests secrets via sensitive_values(os.environ) and then
    redacts every field of the persisted record (command, provenance) with
    them via blind substring replacement. A short/generic value under a
    "sensitive-named" env var (a placeholder, a short synthetic token) can
    coincidentally be a substring of an unrelated generated field like a
    run_id or timestamp — corrupting that field even though it was never a
    secret. Two independent downstream audits (cs-predictor, f1-predictor)
    hit this via CI/sandbox-injected credential-shaped env vars corrupting
    heartbeat run_id/finished_at fields on disk.
    """
    run_id = uuid.uuid4().hex
    short_value = run_id[8:16]  # 8 chars: plausible accidental substring collision
    assert len(short_value) < MIN_SENSITIVE_VALUE_LENGTH

    environment = {"API_TOKEN": short_value}
    secrets = sensitive_values(environment)
    assert secrets == (), "short values must not be auto-harvested from the environment"

    record_text = f"run_id={run_id} finished_at=2026-08-17T14:50:00Z"
    assert redact_text(record_text, secrets) == record_text, "unrelated field must survive untouched"

    # Genuinely long secrets are still harvested and still redacted, per the
    # existing behavior test_redacts_environment_arguments_stdout_and_stderr
    # already covers end to end.
    long_value = "super-secret-" + run_id
    assert len(long_value) >= MIN_SENSITIVE_VALUE_LENGTH
    assert sensitive_values({"API_TOKEN": long_value}) == (long_value,)

    # A short secret explicitly handed to redact_text()/redact() (not
    # auto-harvested from the environment) must still be redacted — this
    # floor only gates automatic environment harvesting.
    assert short_value not in redact_text(f"password={short_value}", (short_value,))
