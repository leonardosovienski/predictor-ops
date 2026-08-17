FROM python:3.14-alpine3.24@sha256:05b2b8b732ecd268fee8727a369f936f022d1321b59befd13c30ede22769dcdc AS builder
RUN apk add --no-cache build-base
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.14-alpine3.24@sha256:05b2b8b732ecd268fee8727a369f936f022d1321b59befd13c30ede22769dcdc AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN addgroup -S predictor && adduser -S -D -H -h /nonexistent -G predictor predictor \
    && mkdir -p /var/lib/predictor-ops && chown predictor:predictor /var/lib/predictor-ops
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/*.whl \
    && python -m pip uninstall --yes msgpack setuptools pip \
    && rm -rf /wheels /root/.cache
USER predictor
WORKDIR /var/lib/predictor-ops
ENTRYPOINT ["predictor-ops"]
CMD ["--version"]
