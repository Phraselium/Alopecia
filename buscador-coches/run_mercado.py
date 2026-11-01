#!/usr/bin/env python3
"""Perfil "mercado": visión global del mercado. Independiente del perfil personal (run.py / config.yaml).

Uso:
  python run_mercado.py                       # recoge todas las fuentes y zonas y regenera mercado.xlsx e informe_mercado.md
  python run_mercado.py --solo cochesnet      # una fuente (se pueden lanzar fuentes distintas en paralelo: son dominios distintos)
  python run_mercado.py --zonas valencia      # solo la zona base
  python run_mercado.py --sin-red             # no pide nada: regenera las salidas con lo guardado
  python run_mercado.py --watch               # repite cada 24 h (mide los días hasta que desaparece cada anuncio)
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from src.http import PoliteClient  # noqa: E402
from src.mercado.collect import FUENTES, collect_one  # noqa: E402
from src.mercado.store import MercadoStore  # noqa: E402


def load(name: str) -> dict:
    return yaml.safe_load((BASE / name).read_text(encoding="utf-8"))


def build(cfg: dict, store: MercadoStore) -> dict:
    from src.mercado.analysis import run_analysis
    from src.mercado.excel import write_workbook
    from src.mercado.report import write_report
    res = run_analysis(store.all(), cfg, BASE)
    write_workbook(BASE / cfg["salida"]["excel"], res)
    write_report(BASE / cfg["salida"]["informe"], res, store)
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo")
    ap.add_argument("--zonas")
    ap.add_argument("--sin-red", action="store_true")
    ap.add_argument("--sin-salidas", action="store_true", help="solo recoger (útil al lanzar fuentes en paralelo)")
    ap.add_argument("--watch", action="store_true")
    a = ap.parse_args()
    cfg = load("config_mercado.yaml")
    (BASE / "logs").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.FileHandler(BASE / cfg["salida"]["log"], encoding="utf-8"), logging.StreamHandler()])
    store = MercadoStore(BASE / cfg["salida"]["db"])
    while True:
        if not a.sin_red:
            client = PoliteClient(cfg["http"], BASE)
            zonas = a.zonas.split(",") if a.zonas else list(cfg["zonas"])
            for f in FUENTES:
                if (a.solo and f != a.solo) or not cfg["fuentes"].get(f, {}).get("activo", True):
                    continue
                for z, (estado, n, req, det) in collect_one(f, client, cfg, store, zonas).items():
                    print(f"  {f:12s} {z:10s} {estado:9s} anuncios={n:<6d} peticiones={req:<5d} {det[:80]}")
        if not a.sin_salidas:
            res = build(cfg, store)
            print(f"Salidas regeneradas: {res['resumen']}")
        if not a.watch:
            return 0
        time.sleep(24 * 3600)


if __name__ == "__main__":
    raise SystemExit(main())
