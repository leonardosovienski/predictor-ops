FROM python:3.13.14-alpine3.24@sha256:399babc8b49529dabfd9c922f2b5eea81d611e4512e3ed250d75bd2e7683f4b0 AS builder
RUN apk add --no-cache build-base
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.13.14-alpine3.24@sha256:399babc8b49529dabfd9c922f2b5eea81d611e4512e3ed250d75bd2e7683f4b0 AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN addgroup -S predictor && adduser -S -D -H -h /nonexistent -G predictor predictor \
    && mkdir -p /var/lib/predictor-ops && chown predictor:predictor /var/lib/predictor-ops
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
USER predictor
WORKDIR /var/lib/predictor-ops
ENTRYPOINT ["predictor-ops"]
CMD ["--version"]
