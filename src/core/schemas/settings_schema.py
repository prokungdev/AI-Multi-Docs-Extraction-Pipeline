from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class DocTypeFilesConfigModel(BaseModel):
    classify_prompt: str
    classify_schema: str
    extract_prompt: str
    extract_schema: str
    extract_rules: str


class DocTypeConfigModel(BaseModel):
    doc_type_id: str
    display_name: str
    is_active: bool = True
    sort_order: int = 1
    files: DocTypeFilesConfigModel



class LoggingConfigModel(BaseModel):
    logs_dir: str = "logs"
    rotation: str = "00:00"
    retention: str = "30 days"
    compression: str = "zip"
    level: str = "INFO"


class ImageProcessingConfigModel(BaseModel):
    supported_input_extensions: List[str]
    processing_format: str
    jpeg_quality: int
    max_dimension: int
    dpi: int
    split_filename_pattern: str
    archive_filename_pattern: str
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
    confidence_high: float
    confidence_low: float
    confidence_review: float
    financial_tolerance: float

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


class AIProviderConfigModel(BaseModel):
    active_provider: str
    billing_tier: str = "paid"
    max_retries: int = 3
    max_images_per_request: int = 50
    gemini: Dict[str, Any] = Field(default_factory=dict)
    openai: Dict[str, Any] = Field(default_factory=dict)


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
    Type-safe, Strictly Validated Pydantic Schema for configs/settings.json
    Fails immediately if any required configuration or threshold is missing or invalid.
    """
    storage_root: str = "storage"
    pipeline_folders: List[str]
    doc_types: List[DocTypeConfigModel]
    logging: LoggingConfigModel
    image_processing: ImageProcessingConfigModel
    validation_thresholds: ValidationThresholdsConfigModel
    ai_provider: AIProviderConfigModel
    ai_pricing: Dict[str, Any] = Field(default_factory=dict)
    database: DatabaseConfigModel

    @model_validator(mode="after")
    def validate_cross_field_rules(self) -> "SystemSettingsModel":
        # 1. Validation Threshold Hierarchy Check
        th = self.validation_thresholds
        if not (th.confidence_low <= th.confidence_review <= th.confidence_high):
            raise ValueError(
                f"Invalid threshold hierarchy: confidence_low ({th.confidence_low}) <= "
                f"confidence_review ({th.confidence_review}) <= confidence_high ({th.confidence_high}) is violated."
            )

        # 2. AI Pricing Parity Check
        active_p = self.ai_provider.active_provider
        provider_cfg = getattr(self.ai_provider, active_p, {})
        if isinstance(provider_cfg, dict) and provider_cfg.get("model_name"):
            model_name = provider_cfg["model_name"]
            pricing_models = self.ai_pricing.get("models", {})
            if pricing_models and model_name not in pricing_models:
                raise ValueError(
                    f"Active AI model '{model_name}' (provider '{active_p}') "
                    f"is missing pricing configuration in 'ai_pricing.models'."
                )
        return self
