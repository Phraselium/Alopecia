"""Alertas por Telegram con un bot propio. Credenciales en .env (fuera del repo):

    TELEGRAM_BOT_TOKEN=123456:ABC...
    TELEGRAM_CHAT_ID=123456789

Sin .env o sin esas claves, las alertas se registran en logs/alertas.log y no se envía nada.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import requests

log = logging.getLogger("notify")


def load_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return {**env, **{k: v for k, v in os.environ.items() if k.startswith("TELEGRAM_")}}


def fmt_eur(x) -> str:
    return "?" if x is None else f"{x:,.0f} €".replace(",", ".")


def message(f: dict) -> str:
    l = f["listing"]
    avisos = [a for a in (f.get("avisos") or "").split("; ") if a]
    estado = "por encima del presupuesto, negociar" if f.get("estado") == "negociar" else "dentro de presupuesto"
    lines = [
        f"🚗 {l.marca or ''} {l.modelo or ''} — {l.anio} · {l.km:,} km".replace(",", "."),
        f"{l.titulo}",
        f"Coste total: {fmt_eur(f['coste']['total'])} ({estado}) · precio {fmt_eur(l.precio)}",
        f"Puntuación: {f['total']:.1f}/100 · {l.plataforma} · {l.vendedor or 'vendedor ?'} · {l.ubicacion or ''}",
    ]
    if avisos:
        lines.append("Avisos: " + "; ".join(avisos[:4]))
    lines.append(l.url)
    return "\n".join(lines)


def send(text: str, env: dict, log_path: Path) -> bool:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(text + "\n---\n")
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        log.info("Telegram sin configurar (.env): alerta solo registrada en %s", log_path)
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text, "disable_web_page_preview": False}, timeout=20)
        if r.status_code != 200:
            log.error("Telegram respondió %s: %s", r.status_code, r.text[:200])
            return False
        return True
    except requests.RequestException as e:
        log.error("No se pudo enviar a Telegram: %s", e)
        return False


def select_alerts(filas: list[dict], new_uids: set[str], already: set[str], cfg: dict) -> list[dict]:
    a = cfg.get("alertas") or {}
    umbral = a.get("umbral_puntuacion", 55)
    estados = {"sí", "negociar"} if a.get("incluir_negociar", True) else {"sí"}
    return [f for f in filas
            if f["listing"].uid in new_uids and f["listing"].uid not in already
            and f.get("estado") in estados and f["total"] >= umbral]
