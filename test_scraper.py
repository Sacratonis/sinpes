import requests
import re

def _scrape_reddit():
    trends = []
    headers = {'User-Agent': 'sinpes-oracle/1.0'}
    
    for sub in ['typography', 'identifythisfont']:
        try:
            resp = requests.get(f'https://www.reddit.com/r/{sub}/hot.json?limit=10', headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for child in data.get('data', {}).get('children', []):
                    title = child.get('data', {}).get('title', '')
                    clean_name = re.sub(r'(?i)(what|font|is|this|identify|\?|please|help|looking|for|anyone|know)', '', title).strip()
                    if len(clean_name) > 4:
                        slug = re.sub(r'[^a-z0-9]+', '-', clean_name.lower()).strip('-')
                        trends.append({
                            'slug': slug[:50],
                            'name': clean_name[:100],
                            'source': f'Reddit (r/{sub})'
                        })
        except Exception as e:
            print(f"Reddit scraping failed for {sub}: {e}")
            
    return trends

print("Testing Reddit Scraper Logic:")
trends = _scrape_reddit()
print(f"Found {len(trends)} trends!")
for t in trends[:5]:
    print(f" - {t['name']} (Slug: {t['slug']}) from {t['source']}")
