from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "service": "predictor_ops",
            "event": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        try:
            from opentelemetry import trace

            context = trace.get_current_span().get_span_context()
            if context.is_valid:
                payload.update(trace_id=f"{context.trace_id:032x}", span_id=f"{context.span_id:016x}")
        except ImportError:
            pass
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def logger() -> logging.Logger:
    value = logging.getLogger("predictor_ops")
    if not value.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        value.addHandler(handler)
        value.setLevel(logging.INFO)
        value.propagate = False
    return value


def configure_otel(endpoint: str | None, service_name: str = "predictor_ops") -> None:
    if not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        raise RuntimeError("install predictor-ops[otel] to export OpenTelemetry traces") from exc
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
