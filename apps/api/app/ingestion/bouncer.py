import os
from fontTools.ttLib import TTFont
from typing import Callable

STATIC_THRESHOLD = 5 * 1024 * 1024
VARIABLE_THRESHOLD = 10 * 1024 * 1024
VARIABLE_SUFFIXES = ('-variable', '-vf', '[wght]', 'var')

def check_size_and_flag(filepath: str, raw_bytes: bytes, alert_callback: Callable[[str], None]) -> None:
    name = os.path.basename(filepath).lower()
    is_variable = any(s in name for s in VARIABLE_SUFFIXES)

    if not is_variable:
        try:
            import io
            font = TTFont(io.BytesIO(raw_bytes))
            is_variable = 'fvar' in font
        except Exception:
            pass  # Unreadable — treated as static for threshold purposes

    threshold = VARIABLE_THRESHOLD if is_variable else STATIC_THRESHOLD
    size = len(raw_bytes)

    if size > threshold:
        alert_callback(
            f"This file is {size // (1024*1024)}MB, larger than usual — "
            f"want to double check it before it goes live?"
        )

def check_editorial_quality(description: str, alert_callback: Callable[[str], None]) -> bool:
    """
    SEO Defense: Prevents thin or templated content from polluting the index 
    and triggering Google's scaled-content penalties.

    Returns True if description passes all checks, False if it should be rejected.
    The caller is responsible for halting the pipeline on False.
    """
    if len(description.strip()) < 250:
        alert_callback("⚠️ Description is too short (< 250 chars). This is a thin-content SEO risk.")
        return False

    # Blocklist of highly generic AI/templated phrases
    generic_patterns = [
        "this is a beautiful font",
        "perfect for any design",
        "designed to make your",
        "is a modern typography",
        "brings a touch of elegance",
        "is a versatile font"
    ]
    
    desc_lower = description.lower()
    for pattern in generic_patterns:
        if pattern in desc_lower:
            alert_callback(f"⚠️ Description contains templated filler: '{pattern}'. Please rewrite for better SEO differentiation.")
            return False

    return True