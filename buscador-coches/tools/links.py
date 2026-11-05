"""Descarga una página (respetando robots/pausas/caché) y lista enlaces que contienen ciertos términos."""
import re, sys
from pathlib import Path
from urllib.parse import urljoin
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.http import PoliteClient, BlockedError, DisallowedError
BASE = Path(__file__).resolve().parents[1]
c = PoliteClient(yaml.safe_load((BASE / "config.yaml").read_text())["http"], BASE)
plat, url, pat = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    r = c.get(plat, url)
except Exception as e:
    print(plat, type(e).__name__, e); sys.exit()
t = r["text"]
print(f"== {plat} {r['status']} {len(t)}B final={r['url']} next_data={'__NEXT_DATA__' in t} nuxt={'__NUXT__' in t} ld={t.count('application/ld+json')}")
links = sorted({urljoin(r["url"], h) for h in re.findall(r'href="([^"#]+)"', t) if re.search(pat, h, re.I)})
for l in links[:25]: print("  ", l)
