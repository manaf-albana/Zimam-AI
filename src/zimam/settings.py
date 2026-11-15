from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    nvidia_api_key: str = ""
    nvidia_model: str = "meta/muse-glimmer-30b"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_max_rpm: int = 30
    bank_base_url: str = "http://127.0.0.1:8765"
    evidence_dir: Path = Path("evidence")
    headed: bool = True
    discovery_max_steps: int = 20
    discovery_timeout_s: int = 180


def load_settings() -> Settings:
    return Settings()
