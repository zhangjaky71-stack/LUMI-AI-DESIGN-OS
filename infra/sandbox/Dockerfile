FROM python:3.12.11-slim-bookworm

LABEL org.opencontainers.image.title="LUMI Sandbox Runtime"
LABEL org.opencontainers.image.version="node21-v1"
LABEL org.opencontainers.image.description="Minimal local/CI execution image for isolated LUMI agent tools"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        fontconfig \
        imagemagick \
        nodejs \
        unzip \
        zip \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /workspace/input /workspace/work /workspace/output \
    && chmod 0555 /workspace /workspace/input /workspace/work /workspace/output

WORKDIR /workspace/work
USER 65532:65532

CMD ["tail", "-f", "/dev/null"]
