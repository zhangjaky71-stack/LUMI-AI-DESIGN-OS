FROM python:3.12-slim-bookworm

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       coreutils \
       ffmpeg \
       fontconfig \
       fonts-dejavu-core \
       imagemagick \
       nodejs \
       unzip \
       zip \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 65532 lumi \
    && useradd --uid 65532 --gid 65532 --no-create-home --home-dir /tmp --shell /usr/sbin/nologin lumi \
    && mkdir -p /opt/lumi /workspace/input /workspace/work /workspace/output \
    && chown -R 65532:65532 /workspace

COPY services/sandbox-runtime/src/lumi_sandbox_runtime/workspace_helper.py /opt/lumi/workspace_helper.py
RUN chmod 0555 /opt/lumi/workspace_helper.py \
    && chmod 0555 /workspace/input \
    && chmod 0700 /workspace/work /workspace/output

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

USER 65532:65532
WORKDIR /workspace/work

CMD ["python", "-c", "import time; time.sleep(10**9)"]
