"""Free Google search-suggestion discovery using inventory-aware query seeds."""

import re

import requests

DEFAULT_SEEDS = ("best fonts for", "free fonts for", "font pairing for", "font alternative to")
FONT_INTENT = re.compile(
    r"(?i)\b(font|fonts|typeface|typography|lettering|calligraphy|serif|sans|script|display|monospace|monospaced)\b"
)


def scrape_autocomplete(seeds: list[str] | tuple[str, ...] | None = None) -> list[dict]:
    results = {}
    for seed in seeds or DEFAULT_SEEDS:
        response = requests.get(
            "https://suggestqueries.google.com/complete/search",
            params={"client": "firefox", "q": seed},
            headers={"User-Agent": "SINPES-Oracle/1.0"},
            timeout=10,
        )
        response.raise_for_status()
        for position, suggestion in enumerate(response.json()[1][:10], start=1):
            name = str(suggestion).strip()
            if not name or name.lower() == seed.lower() or not FONT_INTENT.search(name):
                continue
            key = name.lower()
            current = results.get(key)
            if current is None:
                current = {
                    "name": name,
                    "source": "Google Autocomplete",
                    "region": "global",
                    "score": float(11 - position),
                    "metric": "suggestion_position",
                    "best_position": position,
                    "appearances": 0,
                    "query_seeds": [],
                }
                results[key] = current
            current["appearances"] += 1
            current["query_seeds"].append(seed)
            if position < current["best_position"]:
                current["best_position"] = position
                current["score"] = float(11 - position)
    return list(results.values())
