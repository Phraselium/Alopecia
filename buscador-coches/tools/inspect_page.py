"""Resume los datos estructurados de una página: JSON-LD, estados JS embebidos, precios visibles."""
import json, re, sys
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.http import PoliteClient
BASE = Path(__file__).resolve().parents[1]
c = PoliteClient(yaml.safe_load((BASE / "config.yaml").read_text())["http"], BASE)


def summarize(plat, url):
    try:
        r = c.get(plat, url)
    except Exception as e:
        print(f"== {plat} {url}\n   {type(e).__name__}: {e}"); return None
    t = r["text"]
    print(f"== {plat} {r['status']} {len(t)//1024}KB {r['url']}\n   cache={Path(r['cache_file']).name}")
    for blob in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', t, re.S):
        try:
            d = json.loads(blob)
        except Exception:
            continue
        items = d if isinstance(d, list) else d.get("@graph", [d])
        for it in items:
            if not isinstance(it, dict): continue
            typ = it.get("@type")
            extra = ""
            if typ == "ItemList":
                extra = f"n={len(it.get('itemListElement', []))}"
            elif "offers" in it:
                o = it["offers"]; o = o[0] if isinstance(o, list) else o
                extra = f"price={o.get('price')} name={it.get('name')!r:.60}"
            print(f"   ld+json {typ} {extra}")
    for m in re.finditer(r'(window\.\w+|__NEXT_DATA__|__NUXT_DATA__|__NUXT__|self\.__next_f)\s*', t):
        pass
    states = set(re.findall(r'(__NEXT_DATA__|__NUXT_DATA__|window\.__NUXT__|self\.__next_f|window\.__\w+__|window\.\w*[Ss]tate\w*)', t))
    print("   estados:", sorted(states)[:12])
    prices = re.findall(r'(\d{1,3}(?:\.\d{3})+|\d{4,5})\s?(?:€|&euro;|EUR)', t)
    print("   precios visibles (muestra):", prices[:12], "total", len(prices))
    return r


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        p, u = arg.split("=", 1)
        summarize(p, u)
