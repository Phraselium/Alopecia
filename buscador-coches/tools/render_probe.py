"""Carga una página con Playwright (solo para webs cuyo stock se pinta con JS), guarda en raw/ las
respuestas JSON que hace la propia página y resume precios. Una carga por URL; sin interacción."""
import json, re, sys, time, hashlib
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from src.robots import Robots
import requests
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"

def allowed(url):
    from urllib.parse import urlparse
    p = urlparse(url); r = requests.get(f"{p.scheme}://{p.netloc}/robots.txt", headers={"User-Agent": UA}, timeout=20)
    if r.status_code in (401, 403) or r.status_code >= 500: return False
    return Robots(r.text if r.status_code == 200 else "").can_fetch(UA, url)

plat, url = sys.argv[1], sys.argv[2]
if not allowed(url):
    print("robots.txt no permite", url); sys.exit()
out = BASE / "raw" / plat / "render"; out.mkdir(parents=True, exist_ok=True)
found = []
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium", args=["--headless=new", "--no-sandbox"]); pg = b.new_page(user_agent=UA, locale="es-ES")
    def on_resp(r):
        try:
            if "json" in (r.headers.get("content-type") or "") and r.request.resource_type in ("xhr", "fetch"):
                body = r.text()
                if re.search(r'"(price|precio|amount)\w*"\s*:', body, re.I) and len(body) > 500:
                    h = hashlib.sha1(r.url.encode()).hexdigest()[:12]
                    (out / f"{h}.json").write_text(json.dumps({"url": r.url, "text": body}), encoding="utf-8")
                    found.append((r.url, len(body)))
        except Exception:
            pass
    pg.on("response", on_resp)
    pg.goto(url, wait_until="networkidle", timeout=90000)
    time.sleep(4)
    title = pg.title(); txt = pg.inner_text("body")
    b.close()
print("title:", title)
print("precios en pantalla:", sorted({int(x.replace('.', '')) for x in re.findall(r'(\d{1,3}(?:\.\d{3})+)\s?€', txt)})[:10])
for u, n in found[:10]: print("  JSON", n, u[:200])
