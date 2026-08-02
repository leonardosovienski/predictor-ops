FROM python:3.13.14-slim@sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91 AS builder
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.13.14-slim@sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91 AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN groupadd --system predictor && useradd --system --gid predictor --home-dir /nonexistent predictor \
    && mkdir -p /var/lib/predictor-ops && chown predictor:predictor /var/lib/predictor-ops
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
USER predictor
WORKDIR /var/lib/predictor-ops
ENTRYPOINT ["predictor-ops"]
CMD ["--version"]
