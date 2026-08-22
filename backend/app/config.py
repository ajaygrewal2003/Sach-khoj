from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Sach Khoj"
    app_description: str = "Evidence-grounded Sikhism & Gurbani misinformation validation"
    database_url: str = "sqlite+aiosqlite:///./sachkhoj.db"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    admin_token: str = "dev-admin-token"
    upload_dir: str = "./uploads"
    curated_data_dir: str = "../data/curated"
    banidb_base_url: str = "https://api.banidb.com/v2"
    gurbaninow_base_url: str = "https://api.gurbaninow.com/v2"
    confidence_review_threshold: float = 0.7
    max_upload_bytes: int = 15 * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def curated_path(self) -> Path:
        return Path(self.curated_data_dir).resolve()

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir).resolve()

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
