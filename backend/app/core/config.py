from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "ResearchGraph AI"
    database_url: str = "postgresql+psycopg://researchgraph:change-me-locally@localhost:5432/researchgraph"
    openalex_api_key: str = ""
    analysis_provider: str = "deterministic"
    gemini_api_key: str = ""
    gemini_free_tier_confirmed: bool = False
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_daily_request_limit: int = 5
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
