"""Application settings loaded from environment / .env."""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Load all .env keys into os.environ (needed for GOOGLE_APPLICATION_CREDENTIALS).
load_dotenv(_REPO_ROOT / ".env", override=False)


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

    google_application_credentials: str | None = Field(
        default=None, alias="GOOGLE_APPLICATION_CREDENTIALS"
    )
    gcp_project_id: str | None = Field(default=None, alias="GCP_PROJECT_ID")
    gcp_location: str = Field(default="us-central1", alias="GCP_LOCATION")
    vertex_model_default: str = Field(default="gemini-2.0-flash", alias="VERTEX_MODEL_DEFAULT")
    vertex_model_writing: str = Field(default="gemini-2.0-flash", alias="VERTEX_MODEL_WRITING")

    @field_validator("google_application_credentials", mode="before")
    @classmethod
    def _strip_credential_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip().strip('"').strip("'")
        return cleaned or None

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

    @property
    def gcp_credentials_ready(self) -> bool:
        if self.google_application_credentials:
            return Path(self.google_application_credentials).is_file()
        return bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))

    def apply_gcp_credentials(self) -> None:
        """Ensure Google client libraries see credentials from .env."""
        if self.google_application_credentials:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.google_application_credentials

    def masked_database_url(self) -> str:
        if "@" in self.database_url:
            return self.database_url.split("@", 1)[-1]
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.apply_gcp_credentials()
    return settings
