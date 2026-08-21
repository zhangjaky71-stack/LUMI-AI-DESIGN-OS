ARG UV_BASE_IMAGE=ghcr.io/astral-sh/uv:0.11.28
ARG PYTHON_BASE_IMAGE=python:3.12-slim

FROM ${UV_BASE_IMAGE} AS uv
FROM ${PYTHON_BASE_IMAGE}

COPY --from=uv /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/workspace/.venv/bin:${PATH}"

WORKDIR /workspace
COPY . /workspace

RUN uv sync --all-packages --frozen --no-dev \
    && groupadd --gid 10001 lumi \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin lumi \
    && chown -R lumi:lumi /workspace

EXPOSE 8080
USER 10001:10001

CMD ["lumi-tool-gateway"]
