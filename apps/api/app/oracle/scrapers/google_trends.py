import logging
import requests
import re
import xml.etree.ElementTree as ET

logger = logging.getLogger("sinpes.oracle.google")

def scrape_google_trends() -> list[dict]:
    """Pulls RSS feed from Google Trends daily hot topics."""
    trends = []
    try:
        url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"
        headers = {"User-Agent": "SINPES/1.0 (TrendScraper)"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        for item in root.findall('./channel/item'):
            title_node = item.find('title')
            desc_node = item.find('{https://trends.google.com/trends/trendingsearches/daily}news_item_title')
            
            title = title_node.text if title_node is not None else ""
            desc = desc_node.text if desc_node is not None else ""
            
            combined = f"{title} {desc}".strip()
            
            # Since this is a general feed, we loosely pre-filter for design/font keywords
            # to avoid polluting the oracle hitlist with irrelevant celebrity news
            if combined and re.search(r'(?i)(font|design|typography|logo|brand|type)', combined):
                clean_name = re.sub(r'(?i)(what|font|is|this)', '', title).strip()
                if len(clean_name) > 3:
                    slug = re.sub(r'[^a-z0-9]+', '-', clean_name.lower()).strip('-')
                    trends.append({
                        'slug': slug[:30],
                        'name': clean_name[:30]
                    })
    except Exception as e:
        logger.error(f"Google Trends scraping failure: {e}")
        
    return trends
