import json
import os
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FontIngestionPayload(BaseModel):
    """Versioned contract shared by Telegram ingestion and queue processing."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    version: Literal[1] = 1
    slug: str = Field(min_length=1, max_length=120)
    locale: Literal["en", "es", "pt"] = "en"
    category: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=250)
    use_cases: list[str] = Field(min_length=1)
    keywords: dict[str, str]
    font_files: list[str] = Field(min_length=1)
    image_path: str | None = None
    flagged_as_new_category: bool = False
    translations: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def convert_legacy_metadata(cls, value):
        if not isinstance(value, dict):
            return value
        data = dict(value)
        display_name = data.pop("display_name", "")
        legacy_translations = {
            locale: data.pop(locale)
            for locale in ("en", "es", "pt")
            if data.get(locale)
        }
        if legacy_translations:
            translations = dict(data.get("translations") or {})
            translations.update(legacy_translations)
            data["translations"] = translations
        if not data.get("slug") and display_name:
            ascii_name = unicodedata.normalize("NFKD", display_name).encode("ascii", "ignore").decode()
            data["slug"] = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
        locale = data.get("locale", "en")
        if not data.get("description") and data.get("translations"):
            data["description"] = (
                data["translations"].get(locale)
                or data["translations"].get("en")
                or next(iter(data["translations"].values()))
            )
        if not data.get("keywords") and (display_name or data.get("slug")):
            name = display_name or data["slug"].replace("-", " ").title()
            category = data.get("category", "font")
            uses = ", ".join(data.get("use_cases") or [])
            data["keywords"] = {"en": f"{name}, {category} font, {uses}".strip(", ")}
        return data

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        normalized = value.lower().replace(" ", "-")
        if not all(char.isalnum() or char in "-_" for char in normalized):
            raise ValueError("slug may contain only letters, numbers, hyphens, and underscores")
        return normalized

    @field_validator("use_cases")
    @classmethod
    def clean_use_cases(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("use_cases must contain at least one non-empty value")
        acronyms = {"UI", "UX", "AI", "AR", "VR", "3D"}
        normalized = []
        for item in cleaned:
            words = []
            for word in item.split():
                upper = word.upper()
                words.append(upper if upper in acronyms else word.capitalize())
            normalized.append(" ".join(words))
        return normalized

    @field_validator("keywords")
    @classmethod
    def require_english_keywords(cls, value: dict[str, str]) -> dict[str, str]:
        cleaned = {locale: terms.strip() for locale, terms in value.items() if terms.strip()}
        if not cleaned.get("en"):
            raise ValueError("keywords must include a non-empty 'en' value")
        return cleaned

    @classmethod
    def from_telegram_caption(cls, caption: str, font_files: list[str]) -> "FontIngestionPayload":
        if not caption.strip():
            raise ValueError("the Telegram file must have a JSON caption")
        try:
            data = json.loads(caption)
        except json.JSONDecodeError as exc:
            raise ValueError(f"caption is not valid JSON: {exc.msg} at line {exc.lineno}") from exc
        if not isinstance(data, dict):
            raise ValueError("caption JSON must be an object")
        data["font_files"] = font_files
        return cls.model_validate(data)

    @classmethod
    def from_metadata_file(
        cls,
        metadata_path: str,
        font_files: list[str],
    ) -> "FontIngestionPayload":
        if not metadata_path or not os.path.isfile(metadata_path):
            raise ValueError("the Telegram album must include a readable JSON metadata file")
        try:
            with open(metadata_path, "r", encoding="utf-8") as metadata_file:
                data = json.load(metadata_file)
        except json.JSONDecodeError as exc:
            raise ValueError(f"metadata file is not valid JSON: {exc.msg} at line {exc.lineno}") from exc
        if not isinstance(data, dict):
            raise ValueError("metadata JSON must be an object")
        data["font_files"] = font_files
        # Preview images are generated later by the queue worker.
        data.pop("image_path", None)
        return cls.model_validate(data)

    @classmethod
    def from_queue(cls, text_payload: str, fallback_file: str, image_path: str = "") -> "FontIngestionPayload":
        """Read v1 JSON, legacy raw JSON, or a legacy JSON-file queue item."""
        raw = text_payload
        if text_payload and os.path.isfile(text_payload):
            with open(text_payload, "r", encoding="utf-8") as payload_file:
                raw = payload_file.read()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("queued metadata is neither v1 JSON nor a readable legacy JSON file") from exc
        if not isinstance(data, dict):
            raise ValueError("queued metadata JSON must be an object")

        # Legacy JSON metadata did not carry transport paths or a contract version.
        data.setdefault("version", 1)
        data.setdefault("font_files", [fallback_file])
        data.setdefault("image_path", image_path or None)
        data.setdefault("locale", "en")
        data.setdefault("flagged_as_new_category", False)
        return cls.model_validate(data)
