import re
import io
import copy
from fontTools.ttLib import TTFont

def resolve_display_name(font: TTFont) -> tuple[str, bool]:
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