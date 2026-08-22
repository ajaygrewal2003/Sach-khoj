from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_BACKEND_DIR / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    app_name: str = "Sach Khoj"
    app_description: str = "Evidence-grounded Sikhism & Gurbani misinformation validation"
    database_url: str = "sqlite+aiosqlite:///./sachkhoj.db"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embed_model: str = "text-embedding-3-small"
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
        key = self.openai_api_key.strip()
        if not key or key.lower() in {"test-disabled", "none", "disabled"}:
            return False
        return True


@lru_cache
def get_settings() -> Settings:
    return Settings()
