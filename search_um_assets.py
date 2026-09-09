import requests
import json
import re
import os

token = os.environ.get("ULTRAMAX_SETUP_TOKEN", "").strip()
if not token:
    raise SystemExit("Set ULTRAMAX_SETUP_TOKEN before running this developer utility.")
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

# 1. Fetch setup.html
r = requests.get(f'https://ultramax.vip/setup.html?token={token}', headers=headers, timeout=10)
html = r.text

print('=== Searching UltraMax setup.html for images/GIFs ===')
# Match URLs ending in gif, webp, png, jpg
img_urls = re.findall(r'https?://[^\s"\':<>]+?\.(?:gif|webp|png|jpg|jpeg)', html, re.IGNORECASE)
img_urls = list(dict.fromkeys(img_urls))

for u in img_urls:
    low = u.lower()
    if any(k in low for k in ['paramount', 'hulu', 'netflix', 'disney', 'hbo', 'prime', 'apple', 'peacock']):
        print('  Asset URL:', u)

# 2. Check manifest catalogs for paramount & hulu
mr = requests.get(f'https://ultramax.vip/manifest.json?token={token}', headers=headers, timeout=10)
if mr.status_code == 200:
    cats = mr.json().get('catalogs', [])
    print(f'\n=== UltraMax Manifest Catalogs ({len(cats)} total) ===')
    for cat in cats:
        cid = str(cat.get('id', '')).lower()
        cname = str(cat.get('name', '')).lower()
        if any(k in cid or k in cname for k in ['paramount', 'hulu', 'netflix', 'disney', 'hbo', 'prime']):
            print(f'  Catalog: id={cat.get("id"):30s} | name={cat.get("name")}')
