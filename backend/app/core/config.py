from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from environment variables or backend/.env."""

    app_name: str = "Echo"
    app_env: str = "development"
    frontend_origin: str = "http://localhost:3001"
    frontend_origins: str = ""
    local_storage_path: Path = Path("./data")
    use_mock_ocr: bool = True
    use_mock_tts: bool = True
    tts_provider: str = "azure"
    azure_speech_key: str = ""
    azure_speech_region: str = ""
    azure_speech_voice: str = "zh-HK-HiuMaanNeural"
    edge_tts_voice: str = "zh-CN-XiaoxiaoNeural"
    ffmpeg_path: str = "ffmpeg"
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket_books: str = "documents-source"
    supabase_storage_bucket_pages: str = "documents-pages"
    supabase_storage_bucket_audio: str = "documents-audio"
    ocr_enabled: bool = False
    ocr_text_detection_model: str = "PP-OCRv5_mobile_det"
    ocr_text_recognition_model: str = "PP-OCRv5_mobile_rec"
    ocr_max_image_side: int = Field(default=2000, ge=256)
    ocr_model_cache_path: Path = Path("./data/models/paddlex")
    pdf_text_min_characters: int = Field(default=20, ge=1)
    tts_segment_max_characters: int = Field(default=3000, ge=100)
    tts_segment_target_seconds: int = Field(default=360, ge=30)
    tts_segment_soft_max_seconds: int = Field(default=420, ge=30)
    tts_segment_min_seconds: int = Field(default=30, ge=1)
    max_pdf_size_mb: int = Field(default=50, ge=1)
    max_image_size_mb: int = Field(default=15, ge=1)
    max_image_upload_count: int = Field(default=100, ge=1)
    max_image_pixels: int = Field(default=50_000_000, ge=1)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def max_pdf_size_bytes(self) -> int:
        return self.max_pdf_size_mb * 1024 * 1024

    @property
    def max_image_size_bytes(self) -> int:
        return self.max_image_size_mb * 1024 * 1024

    @property
    def allowed_frontend_origins(self) -> list[str]:
        raw_origins = self.frontend_origins or self.frontend_origin
        return [
            origin.strip().rstrip("/")
            for origin in raw_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
