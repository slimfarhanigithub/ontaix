"""The languages Ontaix speaks: English, French and German.

Two settings use them. A company's model language (`company.language`) is the language of
everything that goes through the model for that company: speech recognition, teach and document
extraction, concept expansion, the instant grammar drafts and the export. A person's portal
language (`account.language`) is the language of the Studio's own labels; unset, the Studio
follows the browser. English is the default of both. Pure constants and functions.
"""

from __future__ import annotations

from typing import Literal

from app.config import SpeechLanguage, SpeechLocale

Language = Literal["en", "fr", "de"]
LANGUAGES: tuple[Language, ...] = ("en", "fr", "de")
DEFAULT_LANGUAGE: Language = "en"
# The English name of each language, for audit sentences and prompts.
LANGUAGE_NAMES: dict[Language, str] = {"en": "English", "fr": "French", "de": "German"}
# The Speech SDK locale of a French or German company; an English company uses the deployment's
# English locale (`ONTAIX_SPEECH_LANGUAGE`).
_LOCALES: dict[Language, SpeechLocale] = {"fr": "fr-FR", "de": "de-DE"}


def speech_locale(language: Language, english: SpeechLanguage) -> SpeechLocale:
    """The recognition locale of a company in `language`: `fr-FR`, `de-DE`, or `english`."""
    return _LOCALES.get(language, english)


def language_of(value: str | None) -> Language:
    """`value` as a language, English for an unknown or missing one."""
    return value if value in LANGUAGES else DEFAULT_LANGUAGE  # type: ignore[return-value]
