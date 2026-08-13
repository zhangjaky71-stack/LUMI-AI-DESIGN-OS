from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    lumi_env: Literal["development", "test", "staging", "production"] = "development"
    lumi_log_level: str = "INFO"
    lumi_version: str = "0.0.0-dev"
    database_url: str | None = None
    migration_database_url: str | None = None
    redis_url: str | None = None
    rabbitmq_url: str | None = None

    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_force_path_style: bool = False

    asset_presign_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    asset_download_ttl_seconds: int = Field(default=300, ge=30, le=3600)
    asset_max_file_bytes: int = Field(default=2_147_483_648, ge=1)
    asset_max_org_storage_bytes: int = Field(default=21_474_836_480, ge=1)
    asset_multipart_threshold_bytes: int = Field(default=104_857_600, ge=5_242_880)
    asset_allow_scan_unavailable: bool = False

    langsmith_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
