import json
import time

import predictor_ops.redaction as redaction
from predictor_ops.redaction import REDACTED, redact, redact_command, redact_text


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
