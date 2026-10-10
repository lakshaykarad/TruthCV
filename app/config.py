from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
 
BASE_DIR = Path(__file__).resolve().parent.parent   # Base Path
PROMPT_DIR = BASE_DIR / "ollama" / "prompts"  # the prompt we give to the ai
TEMPLATE_DIR = BASE_DIR / "app" / "templates" # our code
OUTPUT_DIR = BASE_DIR / "output" # output resume/cover_latter etc. 


class Settings(BaseSettings): 

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,  
        extra="ignore",        
    )
 
    database_url: str
    groq_api_key: str

    app_name: str = "TruthCV"
    app_version: str = "0.1.0"
    debug: bool = False

    ollama_host: str = "http://localhost:11434"
    extraction_model: str = "qwen2.5:3b"
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768
    extraction_timeout: int = 180
    extraction_retries: int = 2
 
    generation_model: str = "openai/gpt-oss-120b"
    generation_timeout: int = 180

    max_batch_size : int = 32
    should_apply_threshold: int = 60
    
    top_k: int = 5
    similarity_threshold: float = 0.4

    strong_threshold  : float = 0.60   
    partial_threshold : float = 0.50
    weak_threshold    : float = 0.40   

    max_upload_mb: int = 10
    max_jd_chars: int = 10_000
    max_questions: int = 5
    daily_limit: int = 5
    
    default_user_email: str = "test@truthcv.com"
    cors_origins: str = (
        "http://localhost:3000,"
        "http://localhost:5500,"
        "http://127.0.0.1:5500,"
        "http://localhost:8000,"
        "http://127.0.0.1:8000"
    )


    @field_validator("embedding_dim")
    @classmethod
    def _dim_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("embedding_dim must be > 0")
        return v

    @field_validator("top_k", "max_questions", "daily_limit")
    @classmethod
    def _must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("value must be > 0")
        return v

    @field_validator("similarity_threshold")
    @classmethod
    def _threshold_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("similarity_threshold must be in [0, 1]")
        return v
 
    @property
    def cors_origins_list(self) -> list[str]:
        """Split the comma-separated string into a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def prompt_dir(self) -> Path:
        return PROMPT_DIR

    @property
    def template_dir(self) -> Path:
        return TEMPLATE_DIR

    @property
    def output_dir(self) -> Path:
        OUTPUT_DIR.mkdir(exist_ok=True)
        return OUTPUT_DIR

settings = Settings()