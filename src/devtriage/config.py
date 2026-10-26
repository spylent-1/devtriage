import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEVTRIAGE_", env_file=".env", extra="ignore")
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    data_dir: Path = Path(".devtriage")
    max_rounds: int = 12
    context_chars: int = 50000
    input_price: float | None = None
    output_price: float | None = None
    rag_enabled: bool = True
    rag_backend: str = "sqlite"
    rag_dsn: SecretStr | None = None
    embedding_base_url: str | None = None
    embedding_model: str | None = None
    embedding_api_key: SecretStr | None = None
    rag_min_similarity: float = Field(default=0.55, ge=-1, le=1)

    def api_key(self):
        # Read dotenv without exposing credentials in diagnostics.
        from dotenv import dotenv_values
        return os.getenv("DEEPSEEK_API_KEY") or dotenv_values(".env").get("DEEPSEEK_API_KEY")


PROJECT = Path(__file__).resolve().parents[2]
LAB = PROJECT / "lab" / "app"
