"""Optional first-run profiles derived from the configured provider's capabilities."""
from tts_app.synthesis import SAMPLE_TEXT

AUDIOBOOK_INSTRUCTIONS = 'Read in a calm long-form audiobook style. Use clear articulation, steady pacing, low vocal fatigue, natural sentence endings, and restrained expressiveness. Avoid theatrical delivery, sales energy, exaggerated intonation, whispering, vocal fry, or sharp news-anchor emphasis.'


def default_profiles(voices):
    profiles = []
    for language, name in [('en', 'English audiobook'), ('zh', 'Chinese audiobook')]:
        candidates = [voice for voice in voices if voice['available'] and language in voice['languages']]
        # Favor instruction-capable narration when available, for either provider.
        selected = next((voice for voice in candidates if voice['supports_instructions']), candidates[0] if candidates else None)
        if selected is not None:
            profiles.append(dict(name=name, voice_id=selected['id'], language=language, speed=1.0,
                instructions=AUDIOBOOK_INSTRUCTIONS if selected['supports_instructions'] else '', preview_text=SAMPLE_TEXT[language]))
    return profiles
