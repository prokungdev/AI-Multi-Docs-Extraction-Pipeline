from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, field_validator, model_validator
from src.infrastructure.core.constants import PipelineStageFolder


class LoggingConfigModel(BaseModel):
    """Application logging settings."""
    logs_dir: str = "logs"
    rotation: str = "00:00"
    retention: str = "30 days"
    compression: str = "zip"
    level: str = "INFO"


class ImageProcessingConfigModel(BaseModel):
    """Image processing and PDF rasterization settings."""
    supported_input_extensions: List[str] = Field(default_factory=lambda: [".pdf", ".jpg", ".jpeg", ".png", ".webp", ".tiff"])
    processing_format: str = "jpg"
    jpeg_quality: int = 85
    max_dimension: int = 1800
    dpi: int = 150
    split_filename_pattern: str = "{doc_type}_{tax_id}_{original_filename}_{batch_id}_p{page_no}"
    archive_filename_pattern: str = "{doc_type}_{tax_id}_{doc_no}_{batch_id}_p{page_no}"
    use_ai_fallback_matching: bool = False

    @field_validator("dpi")
    @classmethod
    def validate_dpi(cls, v: int) -> int:
        if v < 72 or v > 600:
            raise ValueError(f"DPI must be between 72 and 600, got {v}")
        return v

    @field_validator("max_dimension")
    @classmethod
    def validate_max_dim(cls, v: int) -> int:
        if v < 300 or v > 10000:
            raise ValueError(f"Max dimension must be between 300 and 10000, got {v}")
        return v


class ValidationThresholdsConfigModel(BaseModel):
    """Quality and business rule verification thresholds."""
    confidence_high: float = 0.85
    confidence_low: float = 0.60
    confidence_review: float = 0.70
    financial_tolerance: float = 0.05

    @field_validator("confidence_high", "confidence_low", "confidence_review")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError(f"Confidence threshold must be between 0.0 and 1.0, got {v}")
        return v

    @field_validator("financial_tolerance")
    @classmethod
    def validate_tolerance(cls, v: float) -> float:
        if v < 0.0 or v > 100.0:
            raise ValueError(f"Financial tolerance must be positive, got {v}")
        return v


class SQLiteConfigModel(BaseModel):
    db_filename: str = "database/pipeline.db"


class PostgreSQLConfigModel(BaseModel):
    url_env: str = "DATABASE_URL"
    pool_size: int = 10
    max_overflow: int = 20
    pool_recycle: int = 3600
    pool_pre_ping: bool = True


class DatabaseConfigModel(BaseModel):
    active_driver: str = "sqlite"
    echo_sql: bool = False
    sqlite: SQLiteConfigModel = Field(default_factory=SQLiteConfigModel)
    postgresql: PostgreSQLConfigModel = Field(default_factory=PostgreSQLConfigModel)


class SystemSettingsModel(BaseModel):
    """
    Type-safe, Strictly Validated Pydantic Schema for configs/settings.json.
    Fails immediately if any required infrastructure configuration is missing or invalid.
    """
    app_name: Optional[str] = "AI Multi-Docs Extraction Pipeline"
    app_version: Optional[str] = "1.0.0"
    app_description: Optional[str] = None
    storage_root: str = "storage"
    default_company_code: Optional[str] = "C00000_SAMPLE"
    pipeline_folders: List[str] = Field(default_factory=PipelineStageFolder.list_all)
    logging: LoggingConfigModel = Field(default_factory=LoggingConfigModel)
    image_processing: ImageProcessingConfigModel = Field(default_factory=ImageProcessingConfigModel)
    validation_thresholds: Optional[ValidationThresholdsConfigModel] = None
    database: DatabaseConfigModel = Field(default_factory=DatabaseConfigModel)

    @model_validator(mode="after")
    def validate_cross_field_rules(self) -> "SystemSettingsModel":
        if self.validation_thresholds is not None:
            th = self.validation_thresholds
            if not (th.confidence_low <= th.confidence_review <= th.confidence_high):
                raise ValueError(
                    f"Invalid threshold hierarchy: confidence_low ({th.confidence_low}) <= "
                    f"confidence_review ({th.confidence_review}) <= confidence_high ({th.confidence_high}) is violated."
                )
        return self

