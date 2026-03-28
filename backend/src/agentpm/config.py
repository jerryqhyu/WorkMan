from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir, user_data_dir
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENTPM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8765
    mcp_port: int = 8766
    log_level: str = "info"
    default_parallel_runs: int = 2
    planner_heartbeat_seconds: int = 5
    allow_fake_claude: bool = False
    github_token: str | None = Field(default=None, alias="GITHUB_TOKEN")

    @property
    def app_data_dir(self) -> Path:
        return Path(user_data_dir("AgentPM", "AgentPM"))

    @property
    def app_config_dir(self) -> Path:
        return Path(user_config_dir("AgentPM", "AgentPM"))

    @property
    def app_cache_dir(self) -> Path:
        return Path(user_cache_dir("AgentPM", "AgentPM"))

    @property
    def state_dir(self) -> Path:
        return self.app_data_dir / "state"

    @property
    def database_path(self) -> Path:
        return self.state_dir / "app.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"

    @property
    def blob_dir(self) -> Path:
        return self.app_data_dir / "blobs"

    @property
    def repo_cache_dir(self) -> Path:
        return self.app_data_dir / "repos"

    @property
    def worktree_root(self) -> Path:
        return self.app_data_dir / "worktrees"

    @property
    def log_dir(self) -> Path:
        return self.app_data_dir / "logs"

    @property
    def cache_dir(self) -> Path:
        return self.app_cache_dir

    def ensure_dirs(self) -> None:
        for path in [
            self.app_data_dir,
            self.app_config_dir,
            self.app_cache_dir,
            self.state_dir,
            self.blob_dir,
            self.repo_cache_dir,
            self.worktree_root,
            self.log_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
