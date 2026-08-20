from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS = ("staging", "production")


class ContractError(RuntimeError):
    pass


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _service_block(text: str, service: str) -> str:
    marker = f"    {service} = {{"
    start = text.find(marker)
    if start < 0:
        raise ContractError(f"missing service block: {service}")
    brace = text.find("{", start)
    depth = 0
    for index in range(brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ContractError(f"unterminated service block: {service}")


def _require(text: str, scope: str, *needles: str) -> None:
    for needle in needles:
        if needle not in text:
            raise ContractError(f"{scope}: missing {needle}")


def _forbid(text: str, scope: str, *needles: str) -> None:
    for needle in needles:
        if needle in text:
            raise ContractError(f"{scope}: forbidden {needle}")


def _validate_iac(environment: str) -> None:
    path = f"infra/iac/environments/{environment}/app/main.tf"
    text = _read(path)
    _require(text, path, "bucket_names = local.core.bucket_names")

    gateway = _service_block(text, "model-gateway")
    _require(
        gateway,
        f"{path}:model-gateway",
        'LUMI_DATABASE_URL              = local.secret_arns["database/app"]',
        'LUMI_MODEL_PROVIDER_SECRET     = local.secret_arns["providers/model"]',
        'LUMI_MEDIA_PROVIDER_SECRET     = local.secret_arns["providers/media"]',
        'LUMI_MODEL_GATEWAY_AUTH_SECRET = local.secret_arns["internal/model-gateway"]',
        'LUMI_PROVIDER_OUTPUT_BUCKET = local.bucket_names["assets"]',
        "LUMI_S3_REGION              = var.region",
        's3_bucket_arns         = [local.bucket_arns["assets"]]',
    )

    worker = _service_block(text, "worker-media")
    _require(
        worker,
        f"{path}:worker-media",
        "local.model_gateway_environment",
        'LUMI_DATABASE_URL              = local.secret_arns["database/app"]',
        'LUMI_REDIS_URL                 = local.secret_arns["redis/url"]',
        'LUMI_RABBITMQ_URL              = local.secret_arns["rabbitmq/url"]',
        'LUMI_MODEL_GATEWAY_AUTH_SECRET = local.secret_arns["internal/model-gateway"]',
        'LUMI_S3_BUCKET = local.bucket_names["assets"]',
        "LUMI_S3_REGION = var.region",
        'local.bucket_arns["assets"]',
    )
    _forbid(
        worker,
        f"{path}:worker-media",
        "LUMI_MODEL_PROVIDER_SECRET",
        "LUMI_MEDIA_PROVIDER_SECRET",
        'local.secret_arns["providers/model"]',
        'local.secret_arns["providers/media"]',
    )

    dispatcher = _service_block(text, "outbox-dispatcher")
    _require(
        dispatcher,
        f"{path}:outbox-dispatcher",
        "image         = var.worker_media_image",
        '"lumi_worker_media.cli"',
        '"dispatch-outbox"',
        '"--watch"',
        'LUMI_DATABASE_URL = local.secret_arns["database/app"]',
        'LUMI_RABBITMQ_URL = local.secret_arns["rabbitmq/url"]',
        "s3_bucket_arns         = []",
    )
    _forbid(
        dispatcher,
        f"{path}:outbox-dispatcher",
        "LUMI_MODEL_PROVIDER_SECRET",
        "LUMI_MEDIA_PROVIDER_SECRET",
        "LUMI_MODEL_GATEWAY_AUTH_SECRET",
        "LUMI_SANDBOX_RUNTIME_AUTH_SECRET",
        "LUMI_AUTH_SIGNING_SECRET",
        'local.secret_arns["providers/',
        'local.bucket_arns[',
    )

    agent = _service_block(text, "agent-runtime")
    _forbid(
        agent,
        f"{path}:agent-runtime",
        "LUMI_MODEL_PROVIDER_SECRET",
        "LUMI_MEDIA_PROVIDER_SECRET",
        'local.secret_arns["providers/model"]',
        'local.secret_arns["providers/media"]',
    )


def _validate_worker_source() -> None:
    config_path = "apps/worker-media/src/lumi_worker_media/asset_config.py"
    config = _read(config_path)
    _require(
        config,
        config_path,
        'AliasChoices("LUMI_DATABASE_URL", "DATABASE_URL")',
        'AliasChoices("LUMI_S3_BUCKET", "S3_BUCKET")',
        'AliasChoices("LUMI_S3_REGION", "S3_REGION")',
    )

    app_path = "apps/worker-media/src/lumi_worker_media/app.py"
    app = _read(app_path)
    _require(
        app,
        app_path,
        'os.getenv("LUMI_RABBITMQ_URL") or os.getenv("RABBITMQ_URL", "memory://")',
    )

    cli_path = "apps/worker-media/src/lumi_worker_media/cli.py"
    cli = _read(cli_path)
    _require(
        cli,
        cli_path,
        'os.getenv("LUMI_RABBITMQ_URL") or os.getenv("RABBITMQ_URL")',
        'os.getenv("LUMI_DATABASE_URL") or os.getenv("DATABASE_URL")',
        'sub.add_parser("dispatch-outbox")',
        "MediaExternalWaitWakeScheduler(dsn)",
        "MediaJobOutboxDispatcher(dsn, CeleryJobPublisher())",
    )

    for path in (config_path, app_path, cli_path):
        source = _read(path)
        _forbid(
            source,
            path,
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "LUMI_MODEL_PROVIDER_SECRET",
            "LUMI_MEDIA_PROVIDER_SECRET",
        )

    compute_path = "infra/iac/modules/compute/main.tf"
    compute = _read(compute_path)
    _require(
        compute,
        compute_path,
        'contains(["sandbox-runtime", "outbox-dispatcher"], name)',
        "? [var.app_security_group_id, var.sandbox_egress_security_group_id]",
    )


def main() -> int:
    for environment in ENVIRONMENTS:
        _validate_iac(environment)
    _validate_worker_source()
    print("Hosted media runtime deployment contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as exc:
        raise SystemExit(f"hosted media runtime contract failed: {exc}") from exc
