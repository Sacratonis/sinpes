import logging
import re
import requests

from app.core.config import config

logger = logging.getLogger("sinpes.oracle.pinterest")

def scrape_pinterest() -> list[dict]:
    """Read today's growing Pinterest keywords using the official Trends API."""
    token = config.oracle.pinterest_access_token
    if not token:
        raise RuntimeError("PINTEREST_ACCESS_TOKEN is not configured")
    results = []
    headers = {"Authorization": f"Bearer {token}"}
    regions = [value.strip() for value in config.oracle.pinterest_regions.split(",") if value.strip()]
    relevant = re.compile(r"(?i)\b(font|fonts|typeface|typography|lettering|calligraphy|logo|branding|editorial|poster|wedding invitation|ui design|web design)\b")
    errors = []
    successful_regions = 0
    for region in regions:
        try:
            response = requests.get(
                f"https://api.pinterest.com/v5/trends/keywords/{region}/top/growing",
                params={"limit": 50}, headers=headers, timeout=20,
            )
            response.raise_for_status()
            successful_regions += 1
        except requests.RequestException as exc:
            errors.append(f"{region}: {exc}")
            logger.warning("Pinterest region %s failed: %s", region, exc)
            continue
        for item in response.json().get("trends", []):
            keyword = str(item.get("keyword", "")).strip()
            if not keyword or not relevant.search(keyword):
                continue
            results.append({
                "name": keyword,
                "source": "Pinterest",
                "region": region,
                "score": float(item.get("pct_growth_mom") or item.get("pct_growth_wow") or 0),
                "metric": "growth_percent",
            })
    if successful_regions == 0 and errors:
        raise RuntimeError("; ".join(errors))
    return results
