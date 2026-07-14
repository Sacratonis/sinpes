"""Generate the shared ingestion contract from uploaded font files only."""

import json
import os
import re
import unicodedata

import requests
from fontTools.ttLib import TTFont

from app.core.config import config
from app.ingestion.font_converter import resolve_display_name
from app.schemas.ingestion import FontIngestionPayload


def _slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def _without_verified_font_name(value: str, display_name: str) -> str:
    """Remove only the full verified family name before scanning for invented claims."""
    expanded = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", display_name)
    parts = re.findall(r"[A-Za-z0-9]+", expanded)
    if not parts:
        return value
    pattern = r"(?<!\w)" + r"[\s_-]*".join(re.escape(part) for part in parts) + r"(?!\w)"
    return re.sub(pattern, "", value, flags=re.I)


def extract_font_facts(font_files: list[str]) -> dict:
    if not font_files:
        raise ValueError("At least one font file is required")

    families: list[str] = []
    weights: set[int] = set()
    styles: set[str] = set()
    axes: dict[str, dict] = {}
    codepoints: set[int] = set()
    panose = None

    for path in font_files:
        font = TTFont(path, lazy=True)
        try:
            family, _ = resolve_display_name(font, os.path.splitext(os.path.basename(path))[0])
            families.append(family)
            subfamily = ""
            if "name" in font:
                subfamily = font["name"].getDebugName(17) or font["name"].getDebugName(2) or ""
            italic = bool(re.search(r"italic|oblique", subfamily, re.I))
            if "post" in font and getattr(font["post"], "italicAngle", 0):
                italic = True
            styles.add("italic" if italic else "normal")
            if "OS/2" in font:
                os2 = font["OS/2"]
                weights.add(int(getattr(os2, "usWeightClass", 400) or 400))
                if panose is None and getattr(os2, "panose", None):
                    panose = {
                        key: int(value)
                        for key, value in vars(os2.panose).items()
                        if isinstance(value, int)
                    }
            else:
                weights.add(400)
            if "fvar" in font:
                for axis in font["fvar"].axes:
                    axes[axis.axisTag] = {
                        "minimum": axis.minValue,
                        "default": axis.defaultValue,
                        "maximum": axis.maxValue,
                    }
            cmap = font.getBestCmap() or {}
            codepoints.update(cmap)
        finally:
            font.close()

    normalized_families = {_slugify(name) for name in families if name}
    if len(normalized_families) > 1:
        raise ValueError("Uploaded files contain more than one embedded font family")

    coverage = []
    ranges = (
        ("Basic Latin", 0x0020, 0x007E, 0.70),
        ("Latin Extended", 0x0100, 0x024F, 0.25),
        ("Greek", 0x0370, 0x03FF, 0.60),
        ("Cyrillic", 0x0400, 0x04FF, 0.60),
    )
    for label, start, end, minimum_ratio in ranges:
        present = sum(1 for value in codepoints if start <= value <= end)
        if present / (end - start + 1) >= minimum_ratio:
            coverage.append(label)

    display_name = families[0]
    return {
        "display_name": display_name,
        "slug": _slugify(display_name),
        "weights": sorted(weights),
        "styles": sorted(styles),
        "is_variable": bool(axes),
        "variable_axes": axes,
        "mapped_codepoint_count": len(codepoints),
        "unicode_coverage": coverage,
        "panose": panose,
    }


def _validate_generated_metadata(data: dict, facts: dict, font_files: list[str]) -> FontIngestionPayload:
    if not isinstance(data, dict):
        raise ValueError("generated metadata must be an object")
    extra_fields = set(data) - {"category", "translations", "use_cases", "keywords"}
    if extra_fields:
        raise ValueError("generated metadata contains unsupported fields: " + ", ".join(sorted(extra_fields)))
    generated_text = _without_verified_font_name(
        json.dumps(data, ensure_ascii=False), facts.get("display_name", "")
    )
    if re.search(r"\blicen[cs](?:e|ed|es|ing)?\b", generated_text, re.I):
        raise ValueError("generated metadata must not contain license information")
    unsupported_claims = re.compile(
        r"\b(clean|neutral|warm|airy|geometric|elegant|modern|expressive|friendly|distinctive|"
        r"readable|legible|legibility|suitable|ideal|perfect|appearance|visual personality|glyphs?)\b",
        re.I,
    )
    unsupported_match = unsupported_claims.search(generated_text)
    if unsupported_match:
        raise ValueError(
            "generated metadata contains an unsupported design-characteristic claim: "
            + unsupported_match.group(0)
        )
    descriptions = data.get("translations")
    if not isinstance(descriptions, dict):
        raise ValueError("translations must be an object")
    for locale in ("en", "es", "pt"):
        text = descriptions.get(locale)
        if not isinstance(text, str) or len(text.strip()) < 250:
            raise ValueError(f"{locale} description must contain at least 250 characters")
    use_cases = data.get("use_cases")
    if not isinstance(use_cases, list) or not 3 <= len(use_cases) <= 6:
        raise ValueError("use_cases must contain 3-6 short labels")
    if any(not isinstance(value, str) or not 1 <= len(value.split()) <= 4 for value in use_cases):
        raise ValueError("each use case must be a short label of 1-4 words")
    payload_data = {
        "version": 1,
        "slug": facts["slug"],
        "locale": "en",
        "category": data.get("category"),
        "description": descriptions["en"],
        "translations": descriptions,
        "use_cases": data.get("use_cases"),
        "keywords": data.get("keywords"),
        "font_files": font_files,
        "flagged_as_new_category": False,
    }
    return FontIngestionPayload.model_validate(payload_data)


def _build_factual_descriptions(facts: dict, use_cases: list[str]) -> dict[str, str]:
    name = facts["display_name"]
    weights = ", ".join(str(value) for value in facts["weights"])
    styles = ", ".join(facts["styles"])
    coverage_values = facts["unicode_coverage"]
    coverage = ", ".join(coverage_values) or "no complete tracked Unicode block"
    coverage_es = ", ".join({"Basic Latin": "latino básico", "Latin Extended": "latino extendido", "Greek": "griego", "Cyrillic": "cirílico"}.get(value, value) for value in coverage_values) or "ningún bloque Unicode completo supervisado"
    coverage_pt = ", ".join({"Basic Latin": "latim básico", "Latin Extended": "latim estendido", "Greek": "grego", "Cyrillic": "cirílico"}.get(value, value) for value in coverage_values) or "nenhum bloco Unicode completo monitorado"
    axes = ", ".join(facts["variable_axes"]) or "none"
    uses = ", ".join(use_cases)
    use_translations = {
        "ui design": ("diseño de interfaces", "design de interfaces"),
        "ux design": ("diseño de experiencia", "design de experiência"),
        "web design": ("diseño web", "design web"),
        "web interfaces": ("interfaces web", "interfaces web"),
        "mobile apps": ("aplicaciones móviles", "aplicativos móveis"),
        "editorial design": ("diseño editorial", "design editorial"),
        "digital documents": ("documentos digitales", "documentos digitais"),
        "documentation": ("documentación", "documentação"),
        "form labels": ("etiquetas de formulario", "rótulos de formulário"),
        "email templates": ("plantillas de correo", "modelos de e-mail"),
        "branding": ("identidad de marca", "identidade de marca"),
        "brand identity": ("identidad de marca", "identidade de marca"),
        "posters": ("carteles", "cartazes"),
        "headlines": ("titulares", "títulos"),
        "packaging": ("embalaje", "embalagens"),
        "invitations": ("invitaciones", "convites"),
        "social media": ("redes sociales", "redes sociais"),
        "code editors": ("editores de código", "editores de código"),
        "data tables": ("tablas de datos", "tabelas de dados"),
        "signage": ("señalización", "sinalização"),
    }
    uses_es = ", ".join(use_translations.get(value.lower(), (value, value))[0] for value in use_cases)
    uses_pt = ", ".join(use_translations.get(value.lower(), (value, value))[1] for value in use_cases)
    styles_es = ", ".join({"normal": "normal", "italic": "cursiva"}.get(value, value) for value in facts["styles"])
    styles_pt = ", ".join({"normal": "normal", "italic": "itálico"}.get(value, value) for value in facts["styles"])
    axes_es = ", ".join(facts["variable_axes"]) or "ninguno"
    axes_pt = ", ".join(facts["variable_axes"]) or "nenhum"
    count = facts["mapped_codepoint_count"]
    return {
        "en": (
            f"{name} is cataloged in SINPES with {count} mapped Unicode characters. The uploaded family provides "
            f"weight values {weights} and the following styles: {styles}. Verified cmap coverage includes {coverage}. "
            f"Variable axes detected: {axes}. Use it as a comparison option for {uses}. Test the actual font files at "
            "the intended sizes, line lengths, devices, and export formats before selecting them for a final layout."
        ),
        "es": (
            f"{name} está catalogada en SINPES con {count} caracteres Unicode mapeados. La familia subida incluye "
            f"los pesos {weights} y los siguientes estilos: {styles_es}. La cobertura cmap verificada incluye {coverage_es}. "
            f"Ejes variables detectados: {axes_es}. Úsala como opción de comparación para {uses_es}. Prueba los archivos "
            "reales en los tamaños, longitudes de línea, dispositivos y formatos de exportación previstos antes de "
            "seleccionarlos para una composición final."
        ),
        "pt": (
            f"{name} está catalogada no SINPES com {count} caracteres Unicode mapeados. A família enviada inclui "
            f"os pesos {weights} e os seguintes estilos: {styles_pt}. A cobertura cmap verificada inclui {coverage_pt}. "
            f"Eixos variáveis detectados: {axes_pt}. Use-a como opção de comparação para {uses_pt}. Teste os arquivos "
            "reais nos tamanhos, comprimentos de linha, dispositivos e formatos de exportação previstos antes de "
            "selecioná-los para uma composição final."
        ),
    }


def _build_factual_keywords(facts: dict, category: str, use_cases: list[str]) -> dict[str, str]:
    name = facts["display_name"]
    category_name = str(category or "font").replace("-", " ")
    uses = ", ".join(use_cases)
    category_es = {
        "sans serif": "sans serif", "serif": "serif", "script": "script",
        "display": "display", "monospaced": "monoespaciada",
    }.get(category_name.lower(), category_name)
    category_pt = {
        "sans serif": "sans serif", "serif": "serif", "script": "script",
        "display": "display", "monospaced": "monoespaçada",
    }.get(category_name.lower(), category_name)
    return {
        "en": f"{name} font, {category_name} font, {uses}",
        "es": f"fuente {name}, fuente {category_es}, {uses}",
        "pt": f"fonte {name}, fonte {category_pt}, {uses}",
    }


def generate_ingestion_payload(db_conn, font_files: list[str]) -> tuple[FontIngestionPayload, dict]:
    if not config.oracle.groq_api_key:
        raise RuntimeError("GROQ_ORACLE_API_KEY is not configured")
    facts = extract_font_facts(font_files)
    categories = [
        dict(row)
        for row in db_conn.execute("SELECT slug, display_name FROM categories ORDER BY slug").fetchall()
    ]
    prompt = f"""You create multilingual metadata for SINPES, an open-source typography archive.
Return JSON only with category and use_cases. Python creates descriptions and keywords from verified facts.

Rules:
- use_cases must contain 3-6 labels of 1-4 words, such as UI Design or Editorial Design.
- Prefer one existing category slug. Suggest a new concise category only when none fits.
- Only state facts present in Font facts: weights, styles, variable status, axes, mapped character count, and coverage.
- The mapped_codepoint_count is not a glyph count. Always call it mapped characters or codepoints.
- Do not invent or mention designer, foundry, origin, history, release date, license, visual anatomy,
  letterform proportions, spacing, mood, warmth, airiness, or other unsupported characteristics.
- Do not use subjective terms such as clean, neutral, modern, elegant, readable, suitable, or ideal.
- Use cases are recommendation labels, not claims about the font's appearance.
- Never mention licensing.

Font facts: {json.dumps(facts, ensure_ascii=False)}
Existing categories: {json.dumps(categories, ensure_ascii=False)}"""

    last_error = None
    for attempt in range(2):
        content = prompt
        if last_error:
            content += (
                "\n\nThe previous response failed validation: " + last_error +
                ". Rewrite the complete JSON and correct that exact problem."
            )
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {config.oracle.groq_api_key}", "Content-Type": "application/json"},
            json={
                "model": config.oracle.font_metadata_model,
                "messages": [{"role": "user", "content": content}],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
                "max_completion_tokens": 800,
                "reasoning_effort": "low",
            },
            timeout=120,
        )
        response.raise_for_status()
        raw = json.loads(response.json()["choices"][0]["message"]["content"])
        if isinstance(raw, dict):
            raw["translations"] = _build_factual_descriptions(facts, raw.get("use_cases") or [])
            raw["keywords"] = _build_factual_keywords(
                facts, raw.get("category") or "font", raw.get("use_cases") or []
            )
        try:
            return _validate_generated_metadata(raw, facts, font_files), facts
        except (ValueError, TypeError) as exc:
            last_error = str(exc)
    raise ValueError(f"Generated metadata failed validation after one rewrite: {last_error}")
