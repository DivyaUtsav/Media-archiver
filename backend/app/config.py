from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Personal Media Archive API"
    database_url: str = "sqlite:///./media_archive.db"
    archive_root: Path = Path("./archive")
    handoff_root: Path = Path("./handoff")
    ingestion_work_dir: Path = Path("./ingestion_work")
    ingestion_adapter: str = "manifest"
    ingestion_manifest_path: Path = Path("./ingestion_manifest.json")
    default_source_platform: str = "Reddit"
    gallery_dl_targets: str = ""
    gallery_dl_extra_args: str = ""
    enrichment_text_provider: str = "none"
    enrichment_content_provider: str = "none"
    enrichment_art_type_provider: str = "none"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_text_model: str = "qwen2.5:7b-instruct-q4_K_M"
    ollama_vision_model: str = "moondream"
    huggingface_model: str = "Falconsai/nsfw_image_detection"
    enrichment_strict_providers: bool = False
    provider_startup_checks: bool = True
    ingestion_batch_size: int = 20

    model_config = SettingsConfigDict(env_prefix="MEDIA_ARCHIVE_", env_file=".env")


settings = Settings()
