import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
    anthropic_fast_model: str = os.getenv("ANTHROPIC_FAST_MODEL", "claude-3-5-haiku-20241022")

    # Knowledge Brain API
    knowledge_brain_host: str = os.getenv("KNOWLEDGE_BRAIN_HOST", "127.0.0.1")
    knowledge_brain_port: int = int(os.getenv("KNOWLEDGE_BRAIN_PORT", "8000"))
    knowledge_brain_base_url: str = os.getenv("KNOWLEDGE_BRAIN_BASE_URL", "http://127.0.0.1:8000")

    # Ingestion
    support_sitemap_url: str = os.getenv("SUPPORT_SITEMAP_URL", "https://support.brilliantdirectories.com/support/sitemap.xml")
    ingestion_max_concurrency: int = int(os.getenv("INGESTION_MAX_CONCURRENCY", "3"))
    ingestion_polite_delay_sec: float = float(os.getenv("INGESTION_POLITE_DELAY_SEC", "0.5"))
    ingestion_max_retries: int = int(os.getenv("INGESTION_MAX_RETRIES", "3"))

    # Storage Paths
    data_dir: Path = BASE_DIR / "data"
    vector_index_dir: Path = BASE_DIR / "data" / "vector_index"
    sqlite_db_path: Path = BASE_DIR / "data" / "knowledge_brain.db"
    inbox_db_path: Path = BASE_DIR / "data" / "inbox_agent.db"
    meeting_db_path: Path = BASE_DIR / "data" / "meeting_scope.db"

    # Rules
    consecutive_unchanged_threshold: int = int(os.getenv("CONSECUTIVE_UNCHANGED_THRESHOLD", "20"))
    autonomy_trial_enabled: bool = os.getenv("AUTONOMY_TRIAL_ENABLED", "false").lower() == "true"

    class Config:
        arbitrary_types_allowed = True

settings = Settings()

# Ensure directories exist
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.vector_index_dir.mkdir(parents=True, exist_ok=True)
