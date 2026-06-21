"""Application settings loaded from environment / .env."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _REPO_ROOT / ".env"
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
FIREWORKS_API_BASE = "https://api.fireworks.ai/inference/v1"
_OPENAI_BUILTIN_MODELS = frozenset({"gpt-4o-mini", "gpt-4o", "gpt-4", "gpt-4-turbo"})
_VALID_LLM_PROVIDERS = frozenset({"auto", "vertex", "fireworks", "openrouter", "openai"})


def short_model_name(full: str) -> str:
    if not full:
        return "unknown"
    return full.rsplit("/", 1)[-1]

# Load all .env keys into os.environ (needed for GOOGLE_APPLICATION_CREDENTIALS).
load_dotenv(_ENV_PATH, override=False)


class _SettingsCache:
    """Reload settings when .env changes (Streamlit keeps process alive)."""

    def __init__(self) -> None:
        self._mtime: float = -1.0
        self._settings: Settings | None = None

    def get(self) -> "Settings":
        mtime = _ENV_PATH.stat().st_mtime if _ENV_PATH.is_file() else 0.0
        if self._settings is not None and mtime == self._mtime:
            return self._settings
        if mtime != self._mtime:
            load_dotenv(_ENV_PATH, override=True)
            self._mtime = mtime
        self._settings = Settings()
        self._settings.apply_gcp_credentials()
        return self._settings

    def clear(self) -> None:
        self._settings = None


_settings_cache = _SettingsCache()


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
        default="accounts/fireworks/models/deepseek-v4-pro",
        alias="FIREWORKS_MODEL_DEFAULT",
    )
    fireworks_model_ingestion: str = Field(
        default="accounts/fireworks/models/glm-5p2",
        alias="FIREWORKS_MODEL_INGESTION",
    )
    fireworks_model_research: str = Field(
        default="accounts/fireworks/models/kimi-k2p6",
        alias="FIREWORKS_MODEL_RESEARCH",
    )
    fireworks_model_writing: str = Field(
        default="accounts/fireworks/models/deepseek-v4-pro",
        alias="FIREWORKS_MODEL_WRITING",
    )
    fireworks_model_fast: str = Field(
        default="accounts/fireworks/models/deepseek-v4-flash",
        alias="FIREWORKS_MODEL_FAST",
    )

    apollo_api_key: str | None = Field(default=None, alias="APOLLO_API_KEY")
    apollo_enabled: bool = Field(default=False, alias="APOLLO_ENABLED")
    careershift_people_pipeline: bool = Field(default=True, alias="CAREERSHIFT_PEOPLE_PIPELINE")
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
    candidate_years_experience: float | None = Field(default=None, alias="CANDIDATE_YEARS_EXPERIENCE")
    scout_experience_slack_years: float = Field(default=1.0, alias="SCOUT_EXPERIENCE_SLACK_YEARS")
    scout_filter_experience: bool = Field(default=True, alias="SCOUT_FILTER_EXPERIENCE")
    candidate_role_search: str = Field(
        default="machine learning engineer, AI security engineer, cybersecurity engineer, software engineer",
        alias="CANDIDATE_ROLE_SEARCH",
    )
    candidate_visa_status: str = Field(default="F-1 OPT", alias="CANDIDATE_VISA_STATUS")

    notion_api_key: str | None = Field(default=None, alias="NOTION_API_KEY")
    notion_jobs_database_id: str | None = Field(default=None, alias="NOTION_JOBS_DATABASE_ID")
    notion_prop_title: str = Field(default="Name", alias="NOTION_PROP_TITLE")
    notion_prop_company: str = Field(default="Company", alias="NOTION_PROP_COMPANY")
    notion_prop_url: str = Field(default="URL", alias="NOTION_PROP_URL")
    notion_prop_score: str = Field(default="Score", alias="NOTION_PROP_SCORE")
    notion_prop_status: str = Field(default="Status", alias="NOTION_PROP_STATUS")
    notion_prop_source: str | None = Field(default=None, alias="NOTION_PROP_SOURCE")
    notion_prop_opt: str | None = Field(default=None, alias="NOTION_PROP_OPT")

    google_sheets_credentials_json: str | None = Field(
        default=None, alias="GOOGLE_SHEETS_CREDENTIALS_JSON"
    )
    google_sheets_spreadsheet_id: str | None = Field(
        default=None, alias="GOOGLE_SHEETS_SPREADSHEET_ID"
    )

    scout_min_relevance_score: int = Field(default=45, alias="SCOUT_MIN_RELEVANCE_SCORE")
    scout_resume_analysis_threshold: int = Field(
        default=70, alias="SCOUT_RESUME_ANALYSIS_THRESHOLD"
    )
    scout_results_per_term: int = Field(default=20, alias="SCOUT_RESULTS_PER_TERM")
    scout_search_location: str = Field(default="United States", alias="SCOUT_SEARCH_LOCATION")
    scout_target_families: str = Field(
        default="ml,ai_security,cybersecurity,swe",
        alias="SCOUT_TARGET_FAMILIES",
    )
    scout_search_terms: str | None = Field(default=None, alias="SCOUT_SEARCH_TERMS")
    scout_require_opt_mention: bool = Field(default=False, alias="SCOUT_REQUIRE_OPT_MENTION")
    scout_default_resume_label: str | None = Field(
        default=None, alias="SCOUT_DEFAULT_RESUME_LABEL"
    )
    scout_companies_per_run: int = Field(default=15, alias="SCOUT_COMPANIES_PER_RUN")
    scout_company_rescout_hours: int = Field(default=48, alias="SCOUT_COMPANY_RESCOUT_HOURS")
    scout_tavily_enabled: bool = Field(default=True, alias="SCOUT_TAVILY_ENABLED")
    scout_ingestion_batch_size: int = Field(default=6, alias="SCOUT_INGESTION_BATCH_SIZE")
    scout_llm_parallel_workers: int = Field(default=4, alias="SCOUT_LLM_PARALLEL_WORKERS")
    scout_refetch_parallel_workers: int = Field(default=8, alias="SCOUT_REFETCH_PARALLEL_WORKERS")
    scout_tavily_companies_per_run: int = Field(
        default=12, alias="SCOUT_TAVILY_COMPANIES_PER_RUN"
    )

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
        """Pick provider when LLM_PROVIDER=auto (Fireworks-first; Vertex deprecated)."""
        if self.fireworks_configured:
            return "fireworks"
        if self.openai_configured:
            return "openrouter" if self.using_openrouter else "openai"
        if self.vertex_ready:
            return "vertex"
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

    def research_model_name(self) -> str:
        p = self.resolved_llm_provider
        if p == "vertex":
            return self.vertex_model_writing
        if p == "fireworks":
            return self.fireworks_model_research
        return self.openai_model_writing

    def fast_model_name(self) -> str:
        p = self.resolved_llm_provider
        if p == "fireworks":
            return self.fireworks_model_fast
        if p == "vertex":
            return self.vertex_model_ingestion
        return self.openai_model_ingestion

    def writing_model_name(self) -> str:
        p = self.resolved_llm_provider
        if p == "vertex":
            return self.vertex_model_writing
        if p == "fireworks":
            return self.fireworks_model_writing
        return self.openai_model_writing

    def default_model_name(self) -> str:
        p = self.resolved_llm_provider
        if p == "vertex":
            return self.vertex_model_default
        if p == "fireworks":
            return self.fireworks_model_default
        return self.openai_model_default

    def llm_models_summary(self) -> dict[str, str]:
        """Short model ids per pipeline role for UI and logging."""
        return {
            "provider": self.resolved_llm_provider,
            "ingestion": short_model_name(self.ingestion_model_name()),
            "research": short_model_name(self.research_model_name()),
            "writing": short_model_name(self.writing_model_name()),
            "fast": short_model_name(self.fast_model_name()),
            "default": short_model_name(self.default_model_name()),
        }

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
        """Parse comma/semicolon-separated paths; directories expand to *.pdf files."""
        raw = (self.candidate_resume_paths or "").strip()
        if not raw:
            return []
        separator = ";" if ";" in raw and raw.count(",") == 0 else ","
        resolved: list[Path] = []
        for part in raw.split(separator):
            p = part.strip().strip('"').strip("'")
            if not p:
                continue
            path = Path(p).expanduser()
            if not path.is_absolute():
                path = (_REPO_ROOT / path).resolve()
            if path.is_dir():
                resolved.extend(sorted(path.glob("*.pdf")))
            elif path.is_file():
                resolved.append(path)
            else:
                resolved.append(path)  # keep for warning downstream
        return resolved

    def scout_target_families_set(self) -> frozenset[str]:
        raw = (self.scout_target_families or "").strip()
        if not raw:
            return frozenset({"ml", "ai_security", "cybersecurity", "swe"})
        return frozenset(p.strip().lower() for p in raw.split(",") if p.strip())

    def scout_search_terms_list(self) -> list[str]:
        raw = (self.scout_search_terms or "").strip()
        if not raw:
            return []
        return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


def get_settings() -> Settings:
    return _settings_cache.get()


def clear_settings_cache() -> None:
    """Force reload of .env on next get_settings() call."""
    _settings_cache.clear()


get_settings.cache_clear = clear_settings_cache  # type: ignore[attr-defined]
