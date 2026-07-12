import logging
import requests

from app.core.config import config

logger = logging.getLogger("sinpes.oracle.yandex")

def scrape_yandex_trends() -> list[dict]:
    """Discover related font queries using the official Yandex Wordstat API."""
    token = config.oracle.yandex_wordstat_token
    if not token:
        raise RuntimeError("YANDEX_WORDSTAT_TOKEN is not configured")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    seeds = ["free fonts", "serif font", "sans serif font", "script font", "display font", "шрифт"]
    results = []
    for seed in seeds:
        response = requests.post(
            "https://api.wordstat.yandex.net/v1/topRequests",
            headers=headers, json={"phrase": seed, "devices": ["all"]}, timeout=20,
        )
        response.raise_for_status()
        for item in response.json().get("topRequests", [])[:20]:
            phrase = str(item.get("phrase", "")).strip()
            if phrase:
                results.append({
                    "name": phrase, "source": "Yandex", "region": "global",
                    "score": float(item.get("count") or 0), "metric": "monthly_searches",
                })
    return results
