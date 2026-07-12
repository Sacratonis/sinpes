import logging
import requests
import re

logger = logging.getLogger("sinpes.oracle.reddit")

def scrape_reddit() -> list[dict]:
    """Extracts font requests from target typography and design subreddits."""
    trends = []
    headers = {"User-Agent": "SINPES/1.0 (TrendScraper)"}
    
    for sub in ['typography', 'identifythisfont']:
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit=10"
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            for child in data.get("data", {}).get("children", []):
                title = child.get("data", {}).get("title", "")
                if not child.get("data", {}).get("stickied"):
                    # Strip out common request phrases
                    clean_name = re.sub(r'(?i)(what|font|is|this|identify|\?|please|help|looking|for|anyone|know)', '', title).strip()
                    if len(clean_name) > 4:
                        slug = re.sub(r'[^a-z0-9]+', '-', clean_name.lower()).strip('-')
                        trends.append({
                            'slug': slug[:30],
                            'name': clean_name[:30]
                        })
        except Exception as e:
            logger.error(f"Reddit trend scraping failure for {sub}: {e}")
    return trends
