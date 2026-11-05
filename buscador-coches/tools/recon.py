"""Fase 0: reconocimiento. Pide una URL permitida por robots.txt y resume qué estructura de datos trae."""
import json, re, sys
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.http import PoliteClient, BlockedError, DisallowedError

BASE = Path(__file__).resolve().parents[1]
cfg = yaml.safe_load((BASE / "config.yaml").read_text())
c = PoliteClient(cfg["http"], BASE)
for plat, url in [a.split("=", 1) for a in sys.argv[1:]]:
    try:
        r = c.get(plat, url)
    except (BlockedError, DisallowedError) as e:
        print(f"{plat}: {type(e).__name__}: {e}"); continue
    t = r["text"]
    print(f"\n== {plat} {r['status']} {r['content_type']} {len(t)}B cache={r['cache_file']} final={r['url']}")
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
    print("  __NEXT_DATA__:", bool(nd), "| ld+json:", len(re.findall(r'application/ld\+json', t)),
          "| window.__INITIAL:", bool(re.search(r'window\.__\w*(STATE|PROPS|DATA)\w*__?\s*=', t)))
    for m in re.finditer(r'window\.(__\w+)\s*=', t):
        print("  window var:", m.group(1))
    if nd:
        d = json.loads(nd.group(1))
        pp = d.get("props", {}).get("pageProps", {})
        print("  pageProps keys:", list(pp)[:30])
