import re
import io
import hashlib
import logging
import requests
import urllib.parse
import html
from PIL import Image, ImageEnhance, ImageOps
from app.core.config import config

logger = logging.getLogger(__name__)

def validate_image_bytes(data: bytes) -> bytes:
    try:
        image = Image.open(io.BytesIO(data))
        image.verify()
    except Exception as exc:
        raise ValueError("image service returned invalid image data") from exc
    return data

def slugify_filename(target_keyword: str) -> str:
    """'Font Pairing for Design Skills' -> 'font-pairing-for-design-skills'"""
    slug = re.sub(r"[^a-z0-9\s-]", "", target_keyword.lower())
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug

def build_xmp_metadata(title: str, description: str, keywords: list[str], rights: str = "SINPES") -> bytes:
    subjects = "".join(f"<rdf:li>{html.escape(str(kw))}</rdf:li>" for kw in keywords)
    title = html.escape(str(title))
    description = html.escape(str(description))
    rights = html.escape(str(rights))
    return f'''<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/">
   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">{title}</rdf:li></rdf:Alt></dc:title>
   <dc:description><rdf:Alt><rdf:li xml:lang="x-default">{description}</rdf:li></rdf:Alt></dc:description>
   <dc:subject><rdf:Bag>{subjects}</rdf:Bag></dc:subject>
   <dc:rights><rdf:Alt><rdf:li xml:lang="x-default">{rights}</rdf:li></rdf:Alt></dc:rights>
   <photoshop:Credit>SINPES</photoshop:Credit>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>'''.encode("utf-8")

def generate_ai_image_bytes(prompt: str) -> bytes:
    """
    Primary: CF Worker (Flux-1-Schnell)
    Fallback: Pollinations (Flux)
    """
    # 1. Try Cloudflare Worker
    if config.IMAGE_GEN_WORKER_URL and config.IMAGE_GEN_WORKER_SECRET:
        try:
            logger.info(f"Generating image via CF Worker for prompt: {prompt[:50]}...")
            resp = requests.post(
                config.IMAGE_GEN_WORKER_URL,
                json={"prompt": prompt},
                headers={"Authorization": f"Bearer {config.IMAGE_GEN_WORKER_SECRET}"},
                timeout=30
            )
            resp.raise_for_status()
            return validate_image_bytes(resp.content)
        except Exception as e:
            logger.error(f"CF Worker image gen failed, falling back to Pollinations. Error: {e}")

    # 2. Fallback to Pollinations (flux model)
    logger.info("Generating image via Pollinations fallback...")
    encoded_prompt = urllib.parse.quote(prompt)
    pollinations_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?model=flux&nologo=true"
    
    resp = requests.get(pollinations_url, timeout=45)
    resp.raise_for_status()
    return validate_image_bytes(resp.content)

SCENE_DIRECTIONS = (
    "an expansive natural landscape with layered depth and atmospheric light",
    "a quiet botanical environment with tactile organic detail",
    "a culturally significant historic place photographed with restraint",
    "distinctive architecture with strong geometry and human scale",
    "a coastal or waterside setting with weather and natural texture",
    "an intimate craft studio with tools, materials, and evidence of making",
    "an editorial fashion scene built around fabric, silhouette, and movement",
    "a lived-in interior with character, daylight, and meaningful objects",
    "an observational street scene with rhythm, depth, and everyday life",
    "a museum-like still life of unusual objects and tactile materials",
    "a dramatic wilderness detail showing geology, forest, desert, or water",
    "a food or hospitality scene focused on atmosphere rather than branding",
    "an industrial or transport setting with bold structure and perspective",
    "a cultural gathering or performance captured as documentary photography",
    "a scientific, astronomical, or natural-history subject with visual wonder",
    "a sport or movement scene with a strong editorial composition",
)


def build_scene_prompt(category: str, use_cases: list[str], slug: str = "") -> str:
    uses = ", ".join(use_cases) if isinstance(use_cases, list) else str(use_cases)
    identity = f"{slug}|{category}|{uses}".encode("utf-8")
    scene_index = int(hashlib.sha256(identity).hexdigest()[:8], 16) % len(SCENE_DIRECTIONS)
    scene = SCENE_DIRECTIONS[scene_index]
    return (
        f"Create a wide cinematic editorial photograph of {scene}. The art direction should express the mood "
        f"of a {category} typeface used for {uses}, without showing typography. Treat the scene direction as a "
        "creative starting point, not a literal or closed list. Documentary art direction, restrained natural "
        "colors, subtle film grain, tactile materials, confident composition, premium independent design magazine. "
        "Use one clear photographic subject and balanced negative space. "
        "This is a photograph only, not a graphic poster. No captions, no typography, no letters, no words, "
        "no numbers, no logos, no watermarks, no signs, no labels, no interface elements. Wide 16:7 composition."
    )


def compose_font_poster(raw_image_bytes: bytes, display_name: str, font_path: str) -> bytes:
    """Create a text-free hero; the font name is rendered as HTML by the page."""
    source = Image.open(io.BytesIO(raw_image_bytes)).convert("RGB")
    poster = ImageOps.fit(source, (1600, 700), method=Image.Resampling.LANCZOS)
    poster = ImageOps.autocontrast(poster, cutoff=1)
    poster = ImageEnhance.Color(poster).enhance(0.92)
    poster = ImageEnhance.Contrast(poster).enhance(1.04)
    output = io.BytesIO()
    poster.save(output, "JPEG", quality=92, optimize=True)
    return output.getvalue()


def process_hero_image(slug: str, display_name: str, category: str, use_cases: list[str], keyword_phrases: dict, upload_callback, font_path: str = "") -> str:
    """
    Generates the cinematic hero image via AI, injects XMP metadata, and uploads WebP to R2.
    Returns the WebP URL (stable key, no hash — use ?v={updated_at_unix} on the frontend for cache-busting).
    """
    prompt = build_scene_prompt(category, use_cases, slug)
    raw_bytes = generate_ai_image_bytes(prompt)
    poster_bytes = compose_font_poster(raw_bytes, display_name, font_path)
    
    # Use English keyword for filename and XMP — concentrates relevance, avoids multilingual dilution.
    # Localized alt text is the frontend's responsibility (Astro render layer).
    primary_keyword = keyword_phrases.get('en', display_name)
    english_keywords = keyword_phrases.get('en', primary_keyword)
    secondary_keywords = [kw.strip() for kw in english_keywords.split(',')] if isinstance(english_keywords, str) else [english_keywords]
    
    exports = finalize_seo_image(
        raw_image_bytes=poster_bytes,
        target_keyword=primary_keyword,
        secondary_keywords=secondary_keywords,
        image_title=f"{display_name} Typeface"
    )
    
    # Stable R2 key using SEO filename (no hash).
    # Cache-busting is handled at the frontend via ?v={updated_at_unix} query param.
    # Cache-control uses a long TTL but NOT immutable, since the key is stable and may be overwritten.
    seo_key = f"previews/{exports['filename_base']}.webp"
    
    webp_url = upload_callback(
        data=exports['webp_bytes'],
        key=seo_key,
        content_type="image/webp",
        cache_control="public, max-age=31536000"
    )
    
    return webp_url

def finalize_seo_image(
    raw_image_bytes: bytes,
    target_keyword: str,
    secondary_keywords: list[str],
    image_title: str,
    image_description: str = "",
    rights: str = "SINPES",
) -> dict:
    """
    Takes raw bytes from image-gen-worker or Pollinations fallback.
    Converts to WebP with XMP metadata (English-only keywords to preserve per-locale SEO relevance).
    Returns WebP byte stream and SEO filename.

    Note: JPG generation was intentionally removed — it was only needed for the Writer Bot /
    Medium distribution pipeline, not for font product pages. Add it back at the blog
    ingestion layer when needed there.
    """
    img = Image.open(io.BytesIO(raw_image_bytes)).convert("RGB")

    filename = slugify_filename(target_keyword)
    alt_text = image_description or f"{image_title} — {target_keyword}"
    
    xmp = build_xmp_metadata(
        title=image_title,
        description=alt_text,
        keywords=[target_keyword, *secondary_keywords],
        rights=rights,
    )

    # Generate WebP with XMP (Quality 85)
    webp_buf = io.BytesIO()
    img.save(webp_buf, "WEBP", quality=85, xmp=xmp)
    webp_buf.seek(0)

    return {
        "filename_base": filename,
        "alt_text": alt_text,
        "webp_bytes": webp_buf.getvalue(),
    }
