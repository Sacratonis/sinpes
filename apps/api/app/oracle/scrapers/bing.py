import logging
import re
import requests

from app.core.config import config

logger = logging.getLogger("sinpes.oracle.bing")

def scrape_bing_trends() -> list[dict]:
    """Read search queries already generating Bing impressions for SINPES."""
    api_key = config.oracle.bing_webmaster_api_key
    if not api_key:
        raise RuntimeError("BING_WEBMASTER_API_KEY is not configured")
    response = requests.get(
        "https://ssl.bing.com/webmaster/api.svc/json/GetQueryStats",
        params={"apikey": api_key, "siteUrl": config.SITE_URL.rstrip("/") + "/"},
        timeout=20,
    )
    response.raise_for_status()
    relevant = re.compile(r"(?i)\b(font|fonts|typeface|typography|lettering|calligraphy|serif|sans|script|display|monospace)\b")
    trends = []
    for item in response.json().get("d", []):
        query = str(item.get("Query", "")).strip()
        if not query or not relevant.search(query):
            continue
        impressions = int(item.get("Impressions") or 0)
        clicks = int(item.get("Clicks") or 0)
        # High impressions with few clicks represent the clearest SEO opportunity.
        opportunity = impressions * (1 - min(clicks / impressions, 1)) if impressions else 0
        trends.append({
            "name": query, "source": "Bing", "region": "global",
            "score": round(opportunity, 2), "metric": "seo_opportunity",
            "impressions": impressions, "clicks": clicks,
        })
    return trends
