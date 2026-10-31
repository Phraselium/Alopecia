"""Cliente HTTP educado: robots.txt, pausas aleatorias, caché en /raw y detección de bloqueos.

Reglas que aplica siempre:
- Comprueba robots.txt antes de cada URL (si no se puede leer robots.txt, NO pide la URL).
- Una sola petición a la vez por dominio y pausa aleatoria entre peticiones.
- Si detecta captcha / 403 / 429 / página de desafío, lanza BlockedError y la plataforma
  se marca como bloqueada para el resto de la ejecución. No se intenta esquivar.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, urlparse

import requests

from .robots import Robots

log = logging.getLogger("http")

BLOCK_MARKERS = (
    "captcha", "datadome", "px-captcha", "perimeterx", "cf-chl", "challenge-platform",
    "are you a robot", "eres un robot", "access denied", "acceso denegado",
    "incapsula", "distil", "akamai bot",
)


BLOCK_TITLES = ("just a moment", "access denied", "attention required", "pardon our interruption",
                "un momento", "acceso denegado", "are you a robot", "verificaci", "security check", "robot check")


class BlockedError(RuntimeError):
    """La plataforma ha bloqueado o exige captcha."""


class DisallowedError(RuntimeError):
    """robots.txt no permite la URL (o no se pudo leer robots.txt)."""


class PoliteClient:
    def __init__(self, cfg: dict, base_dir: Path):
        self.cfg = cfg
        self.cache_dir = base_dir / cfg.get("cache_dir", "raw")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = cfg.get("cache_ttl_horas", 24) * 3600
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": cfg["user_agent"],
            "Accept-Language": cfg.get("accept_language", "es-ES,es;q=0.9"),
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        })
        self._robots: dict[str, Optional[Robots]] = {}
        self._last_hit: dict[str, float] = {}
        self.blocked: set[str] = set()

    # ---------- robots.txt ----------
    def _robots_for(self, url: str) -> Optional[Robots]:
        """robots.txt del host. None = no se pudo leer o el servidor lo niega -> se trata como prohibido.
        Según RFC 9309, un 4xx (salvo 401/403) o una redirección que no acaba en un robots.txt = sin reglas."""
        p = urlparse(url)
        root = f"{p.scheme}://{p.netloc}"
        if root not in self._robots:
            rp: Optional[Robots]
            try:
                r = self.session.get(root + "/robots.txt", timeout=self.cfg.get("timeout_s", 30))
                if r.status_code >= 500 or r.status_code in (401, 403) or self._looks_blocked(r):
                    log.warning("robots.txt de %s devuelve %s: se trata como prohibido", root, r.status_code)
                    rp = None
                elif r.status_code == 200 and urlparse(r.url).path == "/robots.txt" and "html" not in r.headers.get("content-type", ""):
                    rp = Robots(r.text)
                else:
                    log.warning("%s no tiene robots.txt propio (HTTP %s, final %s): sin reglas", root, r.status_code, r.url)
                    rp = Robots("")
            except requests.RequestException as e:
                log.warning("No se pudo leer robots.txt de %s (%s): se trata como prohibido", root, e)
                rp = None
            self._robots[root] = rp
        return self._robots[root]

    def allowed(self, url: str) -> bool:
        if not self.cfg.get("respetar_robots", True):
            return True
        rp = self._robots_for(url)
        return bool(rp and rp.can_fetch(self.cfg["user_agent"], url))

    # ---------- caché ----------
    def _cache_path(self, platform: str, url: str, params: Optional[dict], body) -> Path:
        key = url + "?" + urlencode(sorted((params or {}).items())) + json.dumps(body, sort_keys=True, default=str)
        h = hashlib.sha1(key.encode()).hexdigest()[:16]
        d = self.cache_dir / platform
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{h}.json"

    # ---------- pausa por dominio ----------
    def _throttle(self, host: str):
        last = self._last_hit.get(host)
        wait = random.uniform(self.cfg["pausa_min_s"], self.cfg["pausa_max_s"])
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < wait:
                time.sleep(wait - elapsed)
        self._last_hit[host] = time.monotonic()

    @staticmethod
    def _looks_blocked(resp: requests.Response) -> bool:
        """Bloqueo = código típico de WAF, título de página de desafío, o marcadores en una página pequeña.
        (Muchas webs reales cargan un SDK de captcha sin bloquear: no basta con encontrar la palabra.)"""
        if resp.status_code in (403, 405, 429, 503):
            return True
        if "html" not in resp.headers.get("content-type", ""):
            return False
        text = resp.text
        m = re.search(r"<title[^>]*>(.*?)</title>", text[:30000], re.S | re.I)
        title = (m.group(1) if m else "").strip().lower()
        if any(x in title for x in BLOCK_TITLES):
            return True
        return len(text) < 60000 and any(mk in text[:20000].lower() for mk in BLOCK_MARKERS)

    def get(self, platform: str, url: str, params: Optional[dict] = None,
            headers: Optional[dict] = None, use_cache: bool = True) -> dict:
        """Devuelve {'status', 'url', 'content_type', 'text', 'cache_file', 'from_cache'}."""
        if platform in self.blocked:
            raise BlockedError(f"{platform} ya marcado como bloqueado en esta ejecución")
        cpath = self._cache_path(platform, url, params, None)
        if use_cache and cpath.exists() and time.time() - cpath.stat().st_mtime < self.ttl:
            data = json.loads(cpath.read_text(encoding="utf-8"))
            data["from_cache"] = True
            data["cache_file"] = str(cpath)
            return data

        full = url + ("?" + urlencode(params) if params else "")
        if not self.allowed(full):
            raise DisallowedError(f"robots.txt no permite {full}")

        host = urlparse(url).netloc
        self._throttle(host)
        log.info("GET %s", full)
        resp = self.session.get(url, params=params, headers=headers or {}, timeout=self.cfg.get("timeout_s", 30))
        if self._looks_blocked(resp):
            self.blocked.add(platform)
            log.error("BLOQUEO en %s: HTTP %s en %s. Se abandona la plataforma en esta ejecución.",
                      platform, resp.status_code, full)
            raise BlockedError(f"{platform}: HTTP {resp.status_code}")
        resp.raise_for_status()
        data = {
            "status": resp.status_code,
            "url": resp.url,
            "content_type": resp.headers.get("content-type", ""),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "text": resp.text,
        }
        cpath.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        data["from_cache"] = False
        data["cache_file"] = str(cpath)
        return data
