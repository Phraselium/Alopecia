"""mercado_ranking.xlsx: anuncios de Valencia ordenados por puntuación, con enlace. Valores calculados por
src/mercado/analysis.py (los mismos que las fórmulas verificadas de mercado.xlsx). Uso: python tools/ranking_mercado.py"""
import sys
from pathlib import Path

import yaml
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from src.excel import BLUE, HDR_FILL, _font  # noqa: E402
from src.mercado.analysis import run_analysis  # noqa: E402
from src.mercado.store import MercadoStore  # noqa: E402

COLS = [("Puesto", None), ("Coche", "titulo"), ("Año", "anio"), ("Km", "km"), ("Precio (€)", "precio"),
        ("Calidad / coste (por 1.000 €)", "ratio"), ("Calidad intrínseca", "calidad_intr"), ("Calidad global", "calidad"),
        ("Coste anual (€)", "coste_anual"), ("Coste total 5 años (€)", "tco"), ("Franja", "franja"), ("Segmento", "segmento"),
        ("Combustible", "combustible"), ("Cambio", "cambio"), ("Etiqueta", "etiqueta"), ("Tipo", "tipo_m"), ("Vendedor", "vendedor"),
        ("Plataforma", "plataforma"), ("Fiabilidad", "fiab"), ("Autonomía real (km)", "autonomia"), ("Aviso batería", "aviso_bat"),
        ("Enlace", "url")]
FMT = {"km": "#,##0", "precio": "#,##0", "coste_anual": "#,##0", "tco": "#,##0", "ratio": "0.00", "calidad_intr": "0.0",
       "calidad": "0.0", "fiab": "0", "autonomia": "0"}
NOTA = ("Valores calculados con src/mercado/analysis.py (los mismos que las fórmulas de mercado.xlsx, verificadas con LibreOffice). "
        "Calidad / coste = calidad intrínseca / (coste anual / 1.000); coste anual con recarga «mixta» para eléctricos.")


def hoja(wb, titulo, ads, clave):
    ws = wb.create_sheet(titulo)
    for i, (h, k) in enumerate(COLS, 1):
        c = ws.cell(1, i, h)
        c.font = Font(bold=True)
        c.fill = HDR_FILL
        c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.cell(1, 1).comment = Comment(NOTA, "mercado")
    for r, a in enumerate(sorted(ads, key=lambda a: -a[clave]), 2):
        for i, (h, k) in enumerate(COLS, 1):
            v = r - 1 if k is None else a.get(k)
            if k == "url" and v:
                c = ws.cell(r, i, "abrir anuncio")
                c.hyperlink = v
                c.font = Font(color="0563C1", underline="single")
                continue
            c = ws.cell(r, i, v)
            c.font = _font(BLUE)
            if k in FMT:
                c.number_format = FMT[k]
    for i, w in enumerate([7, 48, 6, 10, 10, 11, 10, 10, 10, 11, 12, 12, 11, 11, 8, 10, 11, 12, 9, 10, 22, 14], 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    ws.auto_filter.ref = f"A1:{ws.cell(1, len(COLS)).column_letter}{len(ads) + 1}"
    ws.freeze_panes = None


if __name__ == "__main__":
    cfg = yaml.safe_load((BASE / "config_mercado.yaml").read_text(encoding="utf-8"))
    res = run_analysis(MercadoStore(BASE / cfg["salida"]["db"]).all(), cfg, BASE)
    ads = res["base_ads"]
    wb = Workbook()
    wb.remove(wb.active)
    hoja(wb, "Por calidad-coste", ads, "ratio")
    hoja(wb, "Por calidad global", ads, "calidad")
    out = BASE / "mercado_ranking.xlsx"
    wb.save(out)
    print(out, len(ads))
