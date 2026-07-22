from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from environment variables or backend/.env."""

    app_name: str = "Echo"
    app_env: str = "development"
    frontend_origin: str = "http://localhost:3001"
    local_storage_path: Path = Path("./data")
    use_mock_ocr: bool = True
    use_mock_tts: bool = True
    ocr_enabled: bool = False
    ocr_text_detection_model: str = "PP-OCRv5_mobile_det"
    ocr_text_recognition_model: str = "PP-OCRv5_mobile_rec"
    ocr_max_image_side: int = Field(default=2000, ge=256)
    ocr_model_cache_path: Path = Path("./data/models/paddlex")
    pdf_text_min_characters: int = Field(default=20, ge=1)
    tts_segment_max_characters: int = Field(default=900, ge=100)
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
