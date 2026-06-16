"""Application settings loaded from environment / .env."""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
FIREWORKS_API_BASE = "https://api.fireworks.ai/inference/v1"
_OPENAI_BUILTIN_MODELS = frozenset({"gpt-4o-mini", "gpt-4o", "gpt-4", "gpt-4-turbo"})
_VALID_LLM_PROVIDERS = frozenset({"auto", "vertex", "fireworks", "openrouter", "openai"})

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
    vertex_model_default: str = Field(default="gemini-2.5-flash", alias="VERTEX_MODEL_DEFAULT")
    vertex_model_ingestion: str = Field(default="gemini-2.5-flash", alias="VERTEX_MODEL_INGESTION")
    vertex_model_writing: str = Field(default="gemini-2.5-pro", alias="VERTEX_MODEL_WRITING")

    @field_validator("google_application_credentials", mode="before")
    @classmethod
    def _strip_credential_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip().strip('"').strip("'")
        return cleaned or None

    @field_validator("openai_api_key", "openai_api_base", mode="before")
    @classmethod
    def _strip_optional_str(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip().strip('"').strip("'")
        return cleaned or None

    @field_validator("fireworks_api_key", "fireworks_api_base", mode="before")
    @classmethod
    def _strip_fireworks_str(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip().strip('"').strip("'")
        return cleaned or None

    @field_validator("llm_provider_choice", mode="before")
    @classmethod
    def _normalize_llm_provider(cls, value: str | None) -> str:
        if not value:
            return "auto"
        return str(value).strip().lower()

    llm_provider_choice: str = Field(default="auto", alias="LLM_PROVIDER")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_api_base: str | None = Field(default=None, alias="OPENAI_API_BASE")
    openai_model_default: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL_DEFAULT")
    openai_model_ingestion: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL_INGESTION")
    openai_model_writing: str = Field(default="gpt-4o", alias="OPENAI_MODEL_WRITING")

    fireworks_api_key: str | None = Field(default=None, alias="FIREWORKS_API_KEY")
    fireworks_api_base: str = Field(default=FIREWORKS_API_BASE, alias="FIREWORKS_BASE_URL")
    fireworks_model_default: str = Field(
        default="accounts/fireworks/models/deepseek-v4-flash",
        alias="FIREWORKS_MODEL_DEFAULT",
    )
    fireworks_model_ingestion: str = Field(
        default="accounts/fireworks/models/deepseek-v4-flash",
        alias="FIREWORKS_MODEL_INGESTION",
    )
    fireworks_model_writing: str = Field(
        default="accounts/fireworks/models/deepseek-v4-pro",
        alias="FIREWORKS_MODEL_WRITING",
    )

    apollo_api_key: str | None = Field(default=None, alias="APOLLO_API_KEY")
    cmu_email_domain: str = Field(default="andrew.cmu.edu", alias="CMU_EMAIL_DOMAIN")
    cmu_school_name: str = Field(default="Carnegie Mellon", alias="CMU_SCHOOL_NAME")
    tavily_api_key: str | None = Field(default=None, alias="TAVILY_API_KEY")

    # Candidate profile for outreach drafts (paths may be absolute or relative to repo root)
    candidate_name: str | None = Field(default=None, alias="CANDIDATE_NAME")
    candidate_linkedin_url: str | None = Field(default=None, alias="CANDIDATE_LINKEDIN_URL")
    candidate_github_url: str | None = Field(default=None, alias="CANDIDATE_GITHUB_URL")
    candidate_website_url: str | None = Field(default=None, alias="CANDIDATE_WEBSITE_URL")
    candidate_resume_paths: str | None = Field(default=None, alias="CANDIDATE_RESUME_PATHS")
    candidate_graduation: str | None = Field(default=None, alias="CANDIDATE_GRADUATION")
    candidate_role_search: str = Field(default="full-time roles", alias="CANDIDATE_ROLE_SEARCH")

    notion_api_key: str | None = Field(default=None, alias="NOTION_API_KEY")
    notion_jobs_database_id: str | None = Field(default=None, alias="NOTION_JOBS_DATABASE_ID")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def vertex_configured(self) -> bool:
        return bool(self.gcp_project_id)

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def fireworks_configured(self) -> bool:
        return bool(self.fireworks_api_key)

    @property
    def vertex_ready(self) -> bool:
        return self.vertex_configured and self.gcp_credentials_ready

    @property
    def llm_configured(self) -> bool:
        return self.vertex_ready or self.fireworks_configured or self.openai_configured

    def _auto_llm_provider(self) -> str:
        """Pick provider when LLM_PROVIDER=auto."""
        if self.vertex_ready:
            return "vertex"
        if self.fireworks_configured:
            return "fireworks"
        if self.openai_configured:
            return "openrouter" if self.using_openrouter else "openai"
        return "none"

    @property
    def resolved_llm_provider(self) -> str:
        choice = self.llm_provider_choice
        if choice == "auto":
            return self._auto_llm_provider()
        if choice not in _VALID_LLM_PROVIDERS:
            return self._auto_llm_provider()
        if choice == "vertex" and self.vertex_ready:
            return "vertex"
        if choice == "fireworks" and self.fireworks_configured:
            return "fireworks"
        if choice == "openrouter" and self.openai_configured and self.using_openrouter:
            return "openrouter"
        if choice == "openai" and self.openai_configured and not self.using_openrouter:
            return "openai"
        # Requested provider not configured — fall back
        return self._auto_llm_provider()

    def llm_configuration_hint(self) -> str:
        return (
            "No LLM configured. Set one of:\n"
            "  • Vertex: GCP_PROJECT_ID + GOOGLE_APPLICATION_CREDENTIALS\n"
            "  • Fireworks: FIREWORKS_API_KEY (see SummerRA/SED/.env)\n"
            "  • OpenRouter: OPENAI_API_KEY=sk-or-... + OPENAI_API_BASE\n"
            "  • OpenAI: OPENAI_API_KEY\n"
            "Optional: LLM_PROVIDER=auto|vertex|fireworks|openrouter|openai"
        )

    def ingestion_model_name(self) -> str:
        p = self.resolved_llm_provider
        if p == "vertex":
            return self.vertex_model_ingestion
        if p == "fireworks":
            return self.fireworks_model_ingestion
        return self.openai_model_ingestion

    def writing_model_name(self) -> str:
        p = self.resolved_llm_provider
        if p == "vertex":
            return self.vertex_model_writing
        if p == "fireworks":
            return self.fireworks_model_writing
        return self.openai_model_writing

    @property
    def is_openrouter_key(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.startswith("sk-or-"))

    @property
    def using_openrouter(self) -> bool:
        if self.openai_api_base and "openrouter.ai" in self.openai_api_base:
            return True
        return self.is_openrouter_key

    @property
    def resolved_openai_api_base(self) -> str | None:
        if self.openai_api_base:
            return self.openai_api_base.rstrip("/")
        if self.is_openrouter_key:
            return OPENROUTER_API_BASE
        return None

    def resolve_openai_model(self, model_name: str) -> str:
        """Map plain OpenAI model IDs to OpenRouter slugs when needed."""
        if not self.using_openrouter:
            return model_name
        if "/" in model_name or model_name.startswith("openrouter"):
            return model_name
        if model_name in _OPENAI_BUILTIN_MODELS:
            return "openrouter/free"
        return model_name

    @property
    def llm_provider(self) -> str:
        return self.resolved_llm_provider

    @property
    def gcp_credentials_ready(self) -> bool:
        if self.google_application_credentials:
            return Path(self.google_application_credentials).is_file()
        return bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))

    def apply_gcp_credentials(self) -> None:
        """Ensure Google client libraries see credentials from .env."""
        if self.google_application_credentials:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.google_application_credentials
        if self.gcp_project_id:
            os.environ.setdefault("GOOGLE_CLOUD_PROJECT", self.gcp_project_id)
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", self.gcp_location)
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")

    def masked_database_url(self) -> str:
        if "@" in self.database_url:
            return self.database_url.split("@", 1)[-1]
        return self.database_url

    def candidate_resume_paths_list(self) -> list[Path]:
        """Parse comma-separated resume paths from CANDIDATE_RESUME_PATHS."""
        raw = (self.candidate_resume_paths or "").strip()
        if not raw:
            return []
        paths: list[Path] = []
        for part in raw.split(","):
            p = part.strip().strip('"').strip("'")
            if not p:
                continue
            path = Path(p).expanduser()
            if not path.is_absolute():
                path = (_REPO_ROOT / path).resolve()
            paths.append(path)
        return paths


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.apply_gcp_credentials()
    return settings
