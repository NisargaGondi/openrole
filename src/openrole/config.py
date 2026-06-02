"""Application settings loaded from environment / .env."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    database_url: str = Field(
        default=f"sqlite:///{_REPO_ROOT / 'data' / 'openrole.db'}",
        alias="DATABASE_URL",
    )

    gcp_project_id: str | None = Field(default=None, alias="GCP_PROJECT_ID")
    gcp_location: str = Field(default="us-central1", alias="GCP_LOCATION")
    vertex_model_default: str = Field(default="gemini-2.0-flash", alias="VERTEX_MODEL_DEFAULT")
    vertex_model_writing: str = Field(default="gemini-2.0-flash", alias="VERTEX_MODEL_WRITING")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    apollo_api_key: str | None = Field(default=None, alias="APOLLO_API_KEY")
    tavily_api_key: str | None = Field(default=None, alias="TAVILY_API_KEY")

    notion_api_key: str | None = Field(default=None, alias="NOTION_API_KEY")
    notion_jobs_database_id: str | None = Field(default=None, alias="NOTION_JOBS_DATABASE_ID")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def vertex_configured(self) -> bool:
        return bool(self.gcp_project_id)

    def masked_database_url(self) -> str:
        if "@" in self.database_url:
            return self.database_url.split("@", 1)[-1]
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
