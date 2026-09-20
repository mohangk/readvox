"""Reviewed offline inventory for Readvox's existing Qwen realtime protocol.

Source: https://www.alibabacloud.com/help/en/model-studio/qwen-tts-voice-list
Reviewed: 2026-09-13 (source updated 2026-09-02).
Only app languages are represented. Dialects are not Mandarin (app ``zh``).
"""
from tts_app.voice_storage import builtin_voice_key

SOURCE_URL = 'https://www.alibabacloud.com/help/en/model-studio/qwen-tts-voice-list'
REVIEWED_AT = '2026-09-13'
INSTRUCTION_MODEL = 'qwen3-tts-instruct-flash-realtime'
FLASH_MODEL = 'qwen3-tts-flash-realtime'

# Each identity has exactly one reviewed binding; dated aliases are not choices.
_PRESETS = (
    ('Cherry', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Serena', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Ethan', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Chelsie', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Momo', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Vivian', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Moon', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Maia', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Kai', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Nofish', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Bella', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Jennifer', FLASH_MODEL, ('en', 'zh')),
    ('Ryan', FLASH_MODEL, ('en', 'zh')),
    ('Katerina', FLASH_MODEL, ('en', 'zh')),
    ('Aiden', FLASH_MODEL, ('en', 'zh')),
    ('Eldric Sage', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Mia', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Mochi', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Bellona', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Vincent', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Bunny', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Neil', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Elias', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Arthur', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Nini', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Seren', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Pip', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Stella', INSTRUCTION_MODEL, ('en', 'zh')),
    ('Bodega', FLASH_MODEL, ('en', 'zh')),
    ('Sonrisa', FLASH_MODEL, ('en', 'zh')),
    ('Alek', FLASH_MODEL, ('en', 'zh')),
    ('Dolce', FLASH_MODEL, ('en', 'zh')),
    ('Sohee', FLASH_MODEL, ('en', 'zh')),
    ('Ono Anna', FLASH_MODEL, ('en', 'zh')),
    ('Lenn', FLASH_MODEL, ('en', 'zh')),
    ('Emilien', FLASH_MODEL, ('en', 'zh')),
    ('Andre', FLASH_MODEL, ('en', 'zh')),
    ('Radio Gol', FLASH_MODEL, ('en', 'zh')),
    ('Jada', FLASH_MODEL, ('en',)),
    ('Dylan', FLASH_MODEL, ('en',)),
    ('Li', FLASH_MODEL, ('en',)),
    ('Marcus', FLASH_MODEL, ('en',)),
    ('Roy', FLASH_MODEL, ('en',)),
    ('Peter', FLASH_MODEL, ('en',)),
    ('Sunny', FLASH_MODEL, ('en',)),
    ('Eric', FLASH_MODEL, ('en',)),
    ('Rocky', FLASH_MODEL, ('en',)),
    ('Kiki', FLASH_MODEL, ('en',)),
)


def qwen_voice_definitions():
    return [dict(key=builtin_voice_key('qwen', raw), provider='qwen',
        provider_voice_id=raw, name=raw, kind='builtin', available=True,
        model=model, languages=list(languages), supports_instructions=model == INSTRUCTION_MODEL,
        metadata={'source_url': SOURCE_URL, 'reviewed_at': REVIEWED_AT})
        for raw, model, languages in _PRESETS]
