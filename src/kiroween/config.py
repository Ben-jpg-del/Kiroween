"""Configuration management using pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Find the project root (where .env should be)
PROJECT_ROOT = Path(__file__).parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Slack MCP Configuration
    slack_mcp_xoxp_token: str = Field(..., description="Slack user OAuth token")
    slack_user_id: str | None = Field(
        default=None, description="Your Slack user ID (e.g., U01234567)"
    )
    slack_mcp_transport: Literal["stdio", "sse", "streamable_http"] = Field(
        default="stdio", description="MCP transport protocol"
    )
    slack_mcp_add_message_tool: bool = Field(
        default=True, description="Enable message posting capability"
    )

    # LLM Configuration
    llm_provider: Literal["openai"] = Field(default="openai")
    openai_api_key: str = Field(..., description="OpenAI API key")
    llm_model: str = Field(default="gpt-4o", description="LLM model identifier")
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)

    # Supabase Configuration
    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_anon_key: str = Field(..., description="Supabase public anon key")
    supabase_service_role_key: str = Field(..., description="Supabase service role key")
    database_url: str = Field(..., description="PostgreSQL connection string")

    # Application Settings
    app_env: Literal["development", "staging", "production"] = Field(default="development")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    # LangSmith (Optional)
    langchain_tracing_v2: bool = Field(default=False)
    langchain_api_key: str | None = Field(default=None)
    langchain_project: str = Field(default="kiroween-slack-agent")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
