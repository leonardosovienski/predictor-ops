FROM python:3.15-alpine3.24@sha256:d44b1254cb92329418d164b22b20d86bbd3869d48e80e09e476531a409a728bb AS builder
RUN apk upgrade --no-cache && apk add --no-cache build-base
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.15-alpine3.24@sha256:d44b1254cb92329418d164b22b20d86bbd3869d48e80e09e476531a409a728bb AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apk upgrade --no-cache \
    && addgroup -S predictor && adduser -S -D -H -h /nonexistent -G predictor predictor \
    && mkdir -p /var/lib/predictor-ops && chown predictor:predictor /var/lib/predictor-ops
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/*.whl \
    && python -m pip uninstall --yes msgpack setuptools pip \
    && rm -rf /wheels /root/.cache
USER predictor
WORKDIR /var/lib/predictor-ops
ENTRYPOINT ["predictor-ops"]
CMD ["--version"]
