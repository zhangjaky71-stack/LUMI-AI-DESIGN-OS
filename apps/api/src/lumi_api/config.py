from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    lumi_env: Literal["development", "test", "staging", "production"] = "development"
    lumi_log_level: str = "INFO"
    lumi_version: str = "0.0.0-dev"
    database_url: str | None = None
    redis_url: str | None = None
    rabbitmq_url: str | None = None
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    langsmith_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
