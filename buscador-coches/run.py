#!/usr/bin/env python3
"""Buscador de coches de segunda mano en Valencia.

Uso:
  python run.py                     # recoge SOLO anuncios nuevos de todas las plataformas activas y regenera salidas
  python run.py --solo wallapop     # una plataforma
  python run.py --sin-red           # no pide nada: regenera ranking.xlsx e informe.md con lo ya guardado
  python run.py --max-paginas 2     # limitar páginas (útil para validar 20-30 anuncios)

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
                    l = src.detail(l)
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
        store.log_run(name, started, estado, n, len(vistos), detalle)
        resumen[name] = {"estado": estado, "nuevos": n, "ya_vistos": len(vistos), "detalle": detalle}
        log.info("%s: %s, %d nuevos, %d ya vistos", name, estado, n, len(vistos))
    return resumen


def build_outputs(cfg: dict, fiscal: dict, rel: dict, store: Store) -> dict:
    p = Params(cfg, fiscal, rel)
    listings = store.all()
    fiables = set()  # motores diésel con fiabilidad respaldada por fuente: ninguno todavía (PENDIENTE)
    res = process(listings, p, fiables, store.market())
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
    write_report(BASE / out["informe"], list(by_uid.values()), p, out["informe_n"], stats)
    with open(BASE / "logs" / "descartados.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["uid", "url", "titulo", "precio", "motivos"])
        for l, motivos in res.descartados:
            w.writerow([l.uid, l.url, l.titulo, l.precio, " | ".join(motivos)])
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo")
    ap.add_argument("--sin-red", action="store_true")
    ap.add_argument("--max-paginas", type=int)
    a = ap.parse_args()
    cfg, fiscal, rel = load_yaml("config.yaml"), load_yaml("fiscal.yaml"), load_yaml("reliability.yaml")
    setup_logging(BASE / cfg["salida"]["log"])
    store = Store(BASE / cfg["salida"]["db"])
    if not a.sin_red:
        for k, v in collect(cfg, store, a.solo, a.max_paginas).items():
            print(f"  {k:12s} {v['estado']:10s} nuevos={v['nuevos']:<4d} ya_vistos={v['ya_vistos']:<4d} {v['detalle'][:80]}")
    stats = build_outputs(cfg, fiscal, rel, store)
    print(f"Salidas regeneradas: {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
