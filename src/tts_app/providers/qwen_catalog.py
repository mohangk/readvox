"""Reviewed offline inventory for Readvox's existing Qwen realtime protocol.

Source: https://www.alibabacloud.com/help/en/model-studio/qwen-tts-voice-list
Reviewed: 2026-10-21 (source updated 2026-10-11).
Only app languages are represented. Dialects are not Mandarin (app ``zh``).
"""
from tts_app.voice_storage import builtin_voice_key

SOURCE_URL = 'https://www.alibabacloud.com/help/en/model-studio/qwen-tts-voice-list'
REVIEWED_AT = '2026-10-21'
FLASH_MODEL = 'qwen3-tts-flash-realtime'

# Each identity has exactly one reviewed binding; dated aliases are not choices.
_PRESETS = (
    ('Cherry', ('en', 'zh')),
    ('Serena', ('en', 'zh')),
    ('Ethan', ('en', 'zh')),
    ('Chelsie', ('en', 'zh')),
    ('Momo', ('en', 'zh')),
    ('Vivian', ('en', 'zh')),
    ('Moon', ('en', 'zh')),
    ('Maia', ('en', 'zh')),
    ('Kai', ('en', 'zh')),
    ('Nofish', ('en', 'zh')),
    ('Bella', ('en', 'zh')),
    ('Jennifer', ('en', 'zh')),
    ('Ryan', ('en', 'zh')),
    ('Katerina', ('en', 'zh')),
    ('Aiden', ('en', 'zh')),
    ('Eldric Sage', ('en', 'zh')),
    ('Mia', ('en', 'zh')),
    ('Mochi', ('en', 'zh')),
    ('Bellona', ('en', 'zh')),
    ('Vincent', ('en', 'zh')),
    ('Bunny', ('en', 'zh')),
    ('Neil', ('en', 'zh')),
    ('Elias', ('en', 'zh')),
    ('Arthur', ('en', 'zh')),
    ('Nini', ('en', 'zh')),
    ('Seren', ('en', 'zh')),
    ('Pip', ('en', 'zh')),
    ('Stella', ('en', 'zh')),
    ('Bodega', ('en', 'zh')),
    ('Sonrisa', ('en', 'zh')),
    ('Alek', ('en', 'zh')),
    ('Dolce', ('en', 'zh')),
    ('Sohee', ('en', 'zh')),
    ('Ono Anna', ('en', 'zh')),
    ('Lenn', ('en', 'zh')),
    ('Emilien', ('en', 'zh')),
    ('Andre', ('en', 'zh')),
    ('Radio Gol', ('en', 'zh')),
    ('Jada', ('en',)),
    ('Dylan', ('en',)),
    ('Li', ('en',)),
    ('Marcus', ('en',)),
    ('Roy', ('en',)),
    ('Peter', ('en',)),
    ('Sunny', ('en',)),
    ('Eric', ('en',)),
    ('Rocky', ('en',)),
    ('Kiki', ('en',)),
)


def qwen_voice_definitions():
    return [dict(key=builtin_voice_key('qwen', raw), provider='qwen',
        provider_voice_id=raw, name=raw, kind='builtin', available=True,
        model=FLASH_MODEL, languages=list(languages), supports_instructions=False,
        metadata={'source_url': SOURCE_URL, 'reviewed_at': REVIEWED_AT})
        for raw, languages in _PRESETS]
