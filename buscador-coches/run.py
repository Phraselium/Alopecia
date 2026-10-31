#!/usr/bin/env python3
"""Buscador de coches de segunda mano en Valencia.

Uso:
  python run.py                     # recoge SOLO anuncios nuevos de todas las plataformas activas y regenera salidas
  python run.py --solo wallapop     # una plataforma
  python run.py --sin-red           # no pide nada: regenera ranking.xlsx e informe.md con lo ya guardado
  python run.py --max-paginas 2     # limitar páginas (útil para validar 20-30 anuncios)
  python run.py --watch             # repite cada 4 h y avisa por Telegram de los anuncios nuevos buenos

Incremental: los anuncios se guardan en data/listings.sqlite. En cada ejecución solo se pide la ficha
de los anuncios cuyo ID no está ya guardado; los ya conocidos solo actualizan 'last_seen'.
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from pathlib import Path

import requests
import yaml

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from src.excel import write_workbook  # noqa: E402
from src.http import BlockedError, DisallowedError, PoliteClient  # noqa: E402
from src.pipeline import enrich, process  # noqa: E402
from src.report import write_report  # noqa: E402
from src.scoring import Params  # noqa: E402
from src.sources import REGISTRY  # noqa: E402
from src.sources.base import NotReadyError  # noqa: E402
from src.store import Store  # noqa: E402


def load_yaml(name: str) -> dict:
    return yaml.safe_load((BASE / name).read_text(encoding="utf-8"))


def setup_logging(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.FileHandler(path, encoding="utf-8"), logging.StreamHandler()])


def collect(cfg: dict, store: Store, solo: str | None, max_paginas: int | None) -> dict:
    log = logging.getLogger("run")
    client = PoliteClient(cfg["http"], BASE)
    resumen = {}
    for name, scfg in cfg["fuentes"].items():
        if solo and name != solo:
            continue
        if not scfg.get("enabled", True):
            continue
        scfg = dict(scfg)
        if max_paginas:
            scfg["max_paginas"] = max_paginas
        started = time.strftime("%Y-%m-%dT%H:%M:%S")
        src = REGISTRY[name](client, cfg, scfg)
        known = store.known(name)
        nuevos, vistos, estado, detalle = [], [], "ok", ""
        try:
            for l in src.search(since=store.last_success(name)):
                if l.uid in known:
                    vistos.append(l.uid)
                    continue
                if src.needs_detail(l):
                    try:
                        l = src.detail(l)
                    except (BlockedError, DisallowedError):
                        raise
                    except requests.RequestException as e:
                        # una ficha caída no para la fuente: no se guarda y se reintenta en la próxima ejecución
                        log.warning("%s: ficha %s no disponible (%s); se reintentará", name, l.url, e)
                        continue
                nuevos.append(enrich(l))
        except NotReadyError as e:
            estado, detalle = "pendiente", str(e)
            log.warning("%s", e)
        except BlockedError as e:
            estado, detalle = "bloqueado", str(e)
            log.error("Plataforma %s bloqueada: %s. Se continúa con las demás.", name, e)
        except DisallowedError as e:
            estado, detalle = "robots", str(e)
            log.error("robots.txt impide %s: %s", name, e)
        except Exception as e:  # noqa: BLE001 - una plataforma rota no debe parar las demás
            estado, detalle = "error", repr(e)
            log.exception("Error en %s", name)
        if getattr(src, "coverage", None):
            detalle = (detalle + " | " if detalle else "") + "cobertura parcial: " + "; ".join(src.coverage)
        store.add_market(src.market)
        n = store.add_new(nuevos)  # se guardan los recogidos aunque la plataforma se corte a medias
        store.touch(vistos)
        if estado == "ok":
            gone = store.mark_missing(name, set(vistos) | {l.uid for l in nuevos}, {m["uid"] for m in src.market},
                                      cfg.get("seguimiento", {}).get("ejecuciones_para_desaparecido", 2))
            if any(gone.values()):
                log.info("%s: marcados como desaparecidos %s", name, gone)
        store.log_run(name, started, estado, n, len(vistos), detalle)
        resumen[name] = {"estado": estado, "nuevos": n, "ya_vistos": len(vistos), "detalle": detalle}
        log.info("%s: %s, %d nuevos, %d ya vistos", name, estado, n, len(vistos))
    return resumen


def load_dgt(cfg: dict, allow_download: bool):
    from src.dgt import DGTIndex
    d = cfg.get("dgt") or {}
    if not d.get("fichero_distintivos", True):
        return None
    ix = DGTIndex(BASE, d.get("max_edad_horas", 24))
    return ix if ix.ensure(cfg["http"]["user_agent"], allow_download=allow_download) else None


def build_outputs(cfg: dict, fiscal: dict, rel: dict, store: Store, allow_download: bool = True) -> dict:
    p = Params(cfg, fiscal, rel)
    listings = store.all()
    fiables = set()
    dgt = load_dgt(cfg, allow_download)
    res = process(listings, p, fiables, store.market(), dgt=dgt)
    out = cfg["salida"]
    by_uid = {f["listing"].uid: f for f in res.filas}
    write_workbook(BASE / out["excel"], [f["listing"] for f in res.filas], res.avisos, p,
                   {f["listing"].uid: f["mercado"] for f in res.filas})
    stats = {"limpios": len(res.limpios), "descartados": len(res.descartados),
             "plataformas": ", ".join(sorted({l.plataforma for l in res.limpios})) or "ninguna"}
    runs = store.db.execute(
        "SELECT plataforma, estado, detalle FROM runs WHERE id IN (SELECT MAX(id) FROM runs GROUP BY plataforma)").fetchall()
    stats["fuentes"] = runs
    stats["desactivadas"] = [k for k, v in cfg["fuentes"].items() if not v.get("enabled", True)]
    from collections import Counter as _C
    stats["etiquetas"] = {"fuente": dict(_C(f["listing"].etiqueta_fuente for f in res.filas)),
                          "dudosas": sum(1 for f in res.filas if f["listing"].etiqueta_dudosa),
                          "descartadas": sum(1 for _l, m in res.descartados if any(x.startswith("filtro: etiqueta") for x in m)),
                          "menor_que_minima": sum(1 for _l, m in res.descartados if any(x.startswith("filtro: etiqueta") and "<" in x for x in m)),
                          "no_confirmada": sum(1 for _l, m in res.descartados if any(x.startswith("filtro: etiqueta no confirmada") for x in m)),
                          "dudosas_fuera": sum(1 for _l, m in res.descartados if any(x.startswith("filtro: etiqueta dudosa") for x in m))}
    stats["embudo"] = res.embudo
    from collections import Counter
    stats["mercado_por_plataforma"] = dict(Counter(m["plataforma"] for m in store.market()))
    stats["ventas"] = store.sale_times()
    for f in res.filas:
        f["avisos"] = res.avisos.get(f["listing"].uid, "")
    write_report(BASE / out["informe"], list(by_uid.values()), p, out["informe_n"], stats)
    with open(BASE / "logs" / "descartados.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["uid", "url", "titulo", "precio", "motivos"])
        for l, motivos in res.descartados:
            w.writerow([l.uid, l.url, l.titulo, l.precio, " | ".join(motivos)])
    stats["_filas"] = res.filas
    stats["_avisos"] = res.avisos
    return stats


def alert(cfg: dict, store: Store, filas: list, avisos: dict, desde: str) -> int:
    from src.notify import load_env, message, select_alerts, send
    if not (cfg.get("alertas") or {}).get("activas", True):
        return 0
    for f in filas:
        f["avisos"] = avisos.get(f["listing"].uid, "")
    sel = select_alerts(filas, store.new_since(desde), store.alerted(), cfg)
    env = load_env(BASE / ".env")
    sent = [f["listing"].uid for f in sel if send(message(f), env, BASE / "logs" / "alertas.log") or True]
    store.mark_alerted(sent)
    return len(sent)


def run_once(cfg, fiscal, rel, store, a) -> None:
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    if not a.sin_red:
        for k, v in collect(cfg, store, a.solo, a.max_paginas).items():
            print(f"  {k:12s} {v['estado']:10s} nuevos={v['nuevos']:<4d} ya_vistos={v['ya_vistos']:<4d} {v['detalle'][:80]}")
    stats = build_outputs(cfg, fiscal, rel, store, allow_download=not a.sin_red)
    filas, avisos = stats.pop("_filas"), stats.pop("_avisos")
    n_al = 0 if a.sin_red else alert(cfg, store, filas, avisos, started)
    print(f"Salidas regeneradas: limpios={stats['limpios']} descartados={stats['descartados']} alertas={n_al} "
          f"etiquetas={stats['etiquetas']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo")
    ap.add_argument("--sin-red", action="store_true")
    ap.add_argument("--max-paginas", type=int)
    ap.add_argument("--watch", action="store_true", help="repite cada alertas.intervalo_horas (por defecto 4 h)")
    a = ap.parse_args()
    cfg, fiscal, rel = load_yaml("config.yaml"), load_yaml("fiscal.yaml"), load_yaml("reliability.yaml")
    setup_logging(BASE / cfg["salida"]["log"])
    store = Store(BASE / cfg["salida"]["db"])
    if not a.watch:
        run_once(cfg, fiscal, rel, store, a)
        return 0
    horas = (cfg.get("alertas") or {}).get("intervalo_horas", 4)
    log = logging.getLogger("watch")
    while True:
        try:
            cfg, fiscal, rel = load_yaml("config.yaml"), load_yaml("fiscal.yaml"), load_yaml("reliability.yaml")
            run_once(cfg, fiscal, rel, store, a)
        except Exception:  # noqa: BLE001 - el modo vigilancia no debe morir por una ejecución fallida
            log.exception("Ejecución fallida; se reintenta en el siguiente ciclo")
        log.info("Siguiente ejecución en %s h (Ctrl+C para parar)", horas)
        time.sleep(horas * 3600)


if __name__ == "__main__":
    raise SystemExit(main())
