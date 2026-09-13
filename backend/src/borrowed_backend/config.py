from datetime import date
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    demo_date: date | None = None
    catalog_path: Path = BACKEND_ROOT / "data/catalog.json"
    state_dir: Path = BACKEND_ROOT / "data/state"
    images_dir: Path = BACKEND_ROOT / "images"

    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    llm_timeout_s: float = Field(default=25, gt=0, le=120)
    debug: bool = False
    mcp_allowed_hosts: list[str] = Field(default_factory=lambda: [
        "127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", "[::1]", "[::1]:*",
    ])
    mcp_allowed_origins: list[str] = Field(default_factory=lambda: [
        "http://127.0.0.1:*", "http://localhost:*",
    ])
