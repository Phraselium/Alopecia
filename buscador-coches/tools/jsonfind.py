"""Busca listas de objetos con precio dentro del JSON embebido de una página cacheada."""
import json, re, sys
def load_text(f): return json.loads(open(f).read())["text"]
def embedded(t):
    out = {}
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
    if m: out["next"] = json.loads(m.group(1))
    m = re.search(r'window\.__APOLLO_STATE__\s*=\s*(\{.*?\});?\s*</script>', t, re.S)
    if m:
        try: out["apollo"] = json.loads(m.group(1))
        except Exception as e: print("apollo parse", e)
    return out
def walk(o, path, hits):
    if isinstance(o, dict):
        for k, v in o.items(): walk(v, f"{path}/{k}", hits)
    elif isinstance(o, list):
        if o and isinstance(o[0], dict) and re.search(r'"(price|precio|priceRaw|finalPrice)\w*"', json.dumps(o[0])[:4000], re.I):
            hits.append((path, len(o), list(o[0])[:40]))
        for i, v in enumerate(o[:3]): walk(v, f"{path}[{i}]", hits)
if __name__ == "__main__":
    t = load_text(sys.argv[1]); e = embedded(t)
    for name, d in e.items():
        hits = []; walk(d, name, hits)
        for h in hits[:10]: print(h[0], h[1], h[2])
