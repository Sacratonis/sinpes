import re
import io
import copy
import unicodedata
from fontTools.ttLib import TTFont

def normalize_display_name(raw_name: str, fallback_slug: str = "") -> str:
    """Turn noisy internal font metadata into a professional family name."""
    name = unicodedata.normalize("NFKC", raw_name or "").strip()
    name = name.replace("_", " ")
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"(?i)\s+letters?\s*\d+\s*[x×х]\s*\d+\s*$", "", name)
    name = re.sub(r"(?i)[\s_-]+(regular|normal|roman)\s*$", "", name)
    name = re.sub(
        r"(?i)[\s_-]+(?:free[\s_-]+)?personal[\s_-]+use(?:[\s_-]+only)?\s*$",
        "",
        name,
    )
    name = re.sub(r"(?i)[\s_-]+(?:demo|trial|evaluation)\s*$", "", name)
    name = re.sub(r"(?i)[\s_-]+non[\s_-]?commercial(?:[\s_-]+use)?\s*$", "", name)
    name = re.sub(r"(?<=[a-z0-9])By(?:[A-Z][a-z0-9]*){2,}$", "", name)
    name = re.sub(
        r"(?i)\s+by\s+[a-z0-9][a-z0-9.&'_-]*(?:\s+[a-z0-9][a-z0-9.&'_-]*){1,5}$",
        "",
        name,
    )
    name = re.sub(r"(?i)\s+(font|typeface)\s*$", "", name)
    name = re.sub(r"\s*[-–—]+\s*$", "", name).strip()

    if not name or name.lower() == "untitled" or len(name) > 80:
        name = fallback_slug.replace("_", " ").replace("-", " ").strip().title()
    if name.islower():
        name = name.title()
    return name


def resolve_display_name(font: TTFont, fallback_slug: str = "") -> tuple[str, bool]:
    name_table = font['name']
    
    # Prioritizes Name ID 16 (Typographic Family), falls back to Name ID 1
    raw_name = (
        name_table.getDebugName(16) or
        name_table.getDebugName(1) or
        "Untitled"
    )

    # Match both "Demo Font" (word boundary) and "FontDemo" (concatenated suffix)
    is_demo = bool(re.search(r'demo', raw_name, re.IGNORECASE))
    clean_name = re.sub(r'\s*demo\s*', '', raw_name, flags=re.IGNORECASE).strip()
    clean_name = normalize_display_name(clean_name, fallback_slug)

    return clean_name, is_demo

def generate_woff2(font: TTFont) -> bytes:
    """
    Generates a compressed .woff2 for web previews.

    Works on a deep copy of the input TTFont to avoid mutating the caller's
    object in place — setting font.flavor = 'woff2' is a side effect that
    would corrupt any subsequent operations on the same TTFont instance.
    """
    font_copy = copy.deepcopy(font)
    out = io.BytesIO()
    font_copy.flavor = 'woff2'
    font_copy.save(out)
    return out.getvalue()
