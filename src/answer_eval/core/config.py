"""Configuration loader and settings management."""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from answer_eval.core.errors import ConfigurationError

# Load .env if present
load_dotenv()


class OllamaSettings(BaseModel):
    """Ollama OpenAI-compatible connection and runtime settings."""

    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen3-vl:4b"
    api_key: str = "ollama"
    timeout_seconds: int = 120
    max_retries: int = 2


class LlamaServerSettings(BaseModel):
    path: str = "llama-server"
    host: str = "127.0.0.1"
    port: int = 8090
    startup_timeout_seconds: int = 120
    health_check_interval_seconds: int = 2
    health_check_retries: int = 30


class StructuredOutputSettings(BaseModel):
    max_repair_retries: int = 2
    validate_json_schema: bool = True


class CacheSettings(BaseModel):
    enabled: bool = True
    backend: str = "filesystem"


class Settings(BaseModel):
    """Application settings loaded from settings.yaml + environment."""

    ai_provider: str = Field(default="ollama")
    active_model_profile: str = Field(default="qwen3_vl_4b")
    log_level: str = Field(default="INFO")
    log_inference_timing: bool = Field(default=True)
    log_memory_snapshots: bool = Field(default=True)

    vram_safety_margin_gb: float = Field(default=1.5)
    max_oom_retries: int = Field(default=3)
    oom_resolution_tiers: list[int] = Field(default_factory=lambda: [1048576, 589824, 262144, 147456])

    models_dir: str = Field(default="models")
    prompts_dir: str = Field(default="src/answer_eval/prompts/templates")
    data_dir: str = Field(default="data")
    cache_dir: str = Field(default="cache")
    benchmarks_dir: str = Field(default="benchmarks")

    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    llama_server: LlamaServerSettings = Field(default_factory=LlamaServerSettings)
    structured_output: StructuredOutputSettings = Field(default_factory=StructuredOutputSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)

    # Base workspace path
    workspace_root: Path = Field(default_factory=lambda: Path(os.getcwd()))

    def get_path(self, relative_path: str) -> Path:
        """Resolve a path relative to workspace_root if not absolute."""
        p = Path(relative_path)
        if p.is_absolute():
            return p
        return self.workspace_root / p


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load settings from yaml file with env var overrides."""
    workspace_root = Path(os.getcwd())
    config_path = workspace_root / "config" / "settings.yaml" if config_path is None else Path(config_path)

    raw_config: dict[str, Any] = {}
    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    raw_config = loaded
        except Exception as e:
            raise ConfigurationError(f"Failed to read settings from {config_path}: {e}") from e

    # Environment variable overrides
    if ai_provider_env := os.getenv("AI_PROVIDER"):
        raw_config["ai_provider"] = ai_provider_env

    if model_profile_env := os.getenv("MODEL_PROFILE"):
        raw_config["active_model_profile"] = model_profile_env

    if vision_model_env := os.getenv("VISION_MODEL"):
        raw_config.setdefault("ollama", {})["model"] = vision_model_env

    if ollama_url_env := os.getenv("OLLAMA_BASE_URL"):
        raw_config.setdefault("ollama", {})["base_url"] = ollama_url_env

    if ollama_key_env := os.getenv("OLLAMA_API_KEY"):
        raw_config.setdefault("ollama", {})["api_key"] = ollama_key_env

    if ollama_timeout_env := os.getenv("OLLAMA_TIMEOUT"):
        raw_config.setdefault("ollama", {})["timeout_seconds"] = int(ollama_timeout_env)

    if ollama_retries_env := os.getenv("OLLAMA_MAX_RETRIES"):
        raw_config.setdefault("ollama", {})["max_retries"] = int(ollama_retries_env)

    if log_level_env := os.getenv("LOG_LEVEL"):
        raw_config["log_level"] = log_level_env

    if server_port_env := os.getenv("LLAMA_SERVER_PORT"):
        raw_config.setdefault("llama_server", {})["port"] = int(server_port_env)

    if server_host_env := os.getenv("LLAMA_SERVER_HOST"):
        raw_config.setdefault("llama_server", {})["host"] = server_host_env

    if server_path_env := os.getenv("LLAMA_SERVER_PATH"):
        raw_config.setdefault("llama_server", {})["path"] = server_path_env

    raw_config["workspace_root"] = workspace_root
    return Settings(**raw_config)
