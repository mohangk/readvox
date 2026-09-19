from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SelectOption:
    value: str | float
    label: str
    language: str | None = None


@dataclass(frozen=True)
class InstructionModelCapabilities:
    option: SelectOption
    voices: tuple[SelectOption, ...]
    supports_instructions: bool = True


@dataclass(frozen=True)
class InstructionSampleCapabilities:
    models: tuple[InstructionModelCapabilities, ...]
    speeds: tuple[SelectOption, ...]
    default_model: str
    default_voice: str


# Legacy non-editor options are projections of the single reviewed inventory.
from tts_app.providers.qwen_catalog import qwen_voice_definitions, INSTRUCTION_MODEL, FLASH_MODEL


def _voice_options(language):
    return tuple(SelectOption(voice['provider_voice_id'], voice['name'], language=language)
        for voice in qwen_voice_definitions() if language in voice['languages'])


QWEN_ENGLISH_VOICES = _voice_options('en')
QWEN_CHINESE_VOICES = _voice_options('zh')
QWEN_INSTRUCTION_MODELS = (
    SelectOption(INSTRUCTION_MODEL, 'Qwen3 TTS Instruct Flash Realtime'),
    SelectOption(INSTRUCTION_MODEL + '-2026-01-22', 'Qwen3 TTS Instruct Flash Realtime 2026-01-22'),
)
QWEN_INSTRUCTION_VOICES = tuple(SelectOption(voice['provider_voice_id'], voice['name'])
    for voice in qwen_voice_definitions() if voice['supports_instructions'])

SPEED_OPTIONS: tuple[SelectOption, ...] = (
    SelectOption(0.75, "0.75x"),
    SelectOption(0.9, "0.9x"),
    SelectOption(1.0, "1x"),
    SelectOption(1.1, "1.1x"),
    SelectOption(1.25, "1.25x"),
    SelectOption(1.5, "1.5x"),
)

# Offline workshop validation retains historical explicit model inputs.
# Profile/editor/runtime synthesis resolve only the flat persisted catalog.
QWEN_INSTRUCTION_SAMPLE_CAPABILITIES = InstructionSampleCapabilities(
    models=tuple(
        InstructionModelCapabilities(option=model, voices=QWEN_INSTRUCTION_VOICES)
        for model in QWEN_INSTRUCTION_MODELS
    ) + (InstructionModelCapabilities(
        option=SelectOption("qwen3-tts-flash-realtime", "Qwen3 TTS Flash Realtime (legacy, no instructions)"),
        # These presets also support Chinese in legacy saved profiles.
        voices=tuple(SelectOption(voice.value, voice.label) for voice in QWEN_ENGLISH_VOICES), supports_instructions=False,
    ),),
    speeds=SPEED_OPTIONS,
    default_model="qwen3-tts-instruct-flash-realtime",
    default_voice="Kai",
)
