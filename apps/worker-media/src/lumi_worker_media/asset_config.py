from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AssetWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    s3_endpoint_url: str | None = None
    s3_bucket: str
    s3_region: str = "us-east-1"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_force_path_style: bool = False
    asset_allow_scan_unavailable: bool = False
    asset_scan_command: str = "clamdscan"
    asset_ffprobe_command: str = "ffprobe"
    asset_ffmpeg_command: str = "ffmpeg"
    asset_max_image_pixels: int = Field(default=100_000_000, ge=1)
    asset_thumbnail_max_px: int = Field(default=512, ge=64, le=4096)
    asset_medium_max_px: int = Field(default=1600, ge=256, le=8192)

    def asyncpg_dsn(self) -> str:
        prefix = "postgresql+asyncpg://"
        if self.database_url.startswith(prefix):
            return "postgresql://" + self.database_url[len(prefix) :]
        if self.database_url.startswith("postgresql://"):
            return self.database_url
        raise RuntimeError("DATABASE_URL must use PostgreSQL")
