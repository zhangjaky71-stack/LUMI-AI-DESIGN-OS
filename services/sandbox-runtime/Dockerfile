FROM ghcr.io/astral-sh/uv:0.11.28 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/workspace/.venv/bin:${PATH}"

WORKDIR /workspace
COPY . /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && uv sync --all-packages --frozen --no-dev \
    && groupadd --gid 10001 lumi \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin lumi \
    && chown -R lumi:lumi /workspace

EXPOSE 8080
USER 10001:10001

CMD ["lumi-sandbox-runtime"]
