"""Shared preview and generation synthesis validation."""
from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator

SAMPLE_TEXT = {
    "en": "This is a short Readvox voice sample. Use it to check the voice, pacing, clarity, and listening comfort before generating the full article.",
    "zh": "这是一个简短的 Readvox 语音示例。请用它来检查声音、语速、清晰度和听感是否适合长时间收听。",
}

SAMPLE_LANGUAGES = {
    "en": "English",
    "zh": "Chinese",
}

MAX_INSTRUCTION_SAMPLE_CHARS = 50_000


class VoiceSampleRequest(BaseModel):
    voice: str
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    language: str = "en"


class SynthesisSettingsRequest(BaseModel):
    # Legacy HTTP input only: it must match the catalog, never overrides it.
    model: str | None = Field(default=None, max_length=120)
    voice: str | None = Field(default=None, min_length=1, max_length=120)
    voice_id: int | None = Field(default=None, gt=0)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    language: str = "en"
    instructions: str = Field(max_length=4000)

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("instructions")
    @classmethod
    def validate_instructions(cls, value: str) -> str:
        return value.strip()


class InstructionVoiceSampleRequest(SynthesisSettingsRequest):
    sample_text: str = Field(max_length=MAX_INSTRUCTION_SAMPLE_CHARS)

    @field_validator("sample_text")
    @classmethod
    def validate_sample_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped


def _validate_language(language: str) -> None:
    if language not in SAMPLE_LANGUAGES:
        raise HTTPException(status_code=400, detail="language must be en or zh")

