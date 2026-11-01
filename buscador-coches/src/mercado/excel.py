"""mercado.xlsx: Anuncios, Precios por modelo, Depreciación, Oferta, Primas, Frontera (con gráfico), Top por franja, Supuestos.

Convención (la misma del perfil personal): azul = dato (anuncio o fuente externa, con la fuente en nota; también los valores
calculados en Python fuera de la hoja, con nota), negro = fórmula de la propia hoja, verde = fórmula que trae datos de otra
hoja o de Supuestos. Sin paneles inmovilizados.
"""
from __future__ import annotations

import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import Reference, ScatterChart, Series
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.formula import ArrayFormula

from ..excel import BLACK, BLUE, GREEN, HDR_FILL, SEC_FONT, Names, _font

FRANJAS = ["0-5000", "5000-10000", "10000-15000", "15000-25000", ">25000"]


# ------------------------------------------------------------------ Supuestos
def build_supuestos(wb, res, names: Names):
    ws = wb.create_sheet("Supuestos")
    cfg, sup, fiscal = res["cfg"], res["sup"], res["fiscal"]
    r = 1
    ws.cell(r, 1, "Supuestos del perfil mercado (cada dato con estado y fuente)").font = SEC_FONT
    r += 2

    def param(name, label, value, estado="", fuente="", color=BLUE):
        nonlocal r
        ws.cell(r, 1, label)
        c = ws.cell(r, 2, value)
        c.font = _font(color)
        ws.cell(r, 3, estado)
        ws.cell(r, 4, fuente)
        names.add(name, f"Supuestos!$B${r}")
        r += 1

    def section(t):
        nonlocal r
        r += 1
        ws.cell(r, 1, t).font = SEC_FONT
        r += 1

    def table(name, rows, hdr, src=""):
        nonlocal r
        for i, h in enumerate(hdr, 1):
            c = ws.cell(r, i, h)
            c.font = Font(bold=True)
            c.fill = HDR_FILL
        r += 1
        t0 = r
        for row in rows:
            for i, v in enumerate(row, 1):
                ws.cell(r, i, v).font = _font(BLUE)
            if src:
                ws.cell(r, len(hdr) + 1, src)
            r += 1
        names.add(name, f"Supuestos!$A${t0}:${get_column_letter(len(hdr))}${r - 1}")

    glob, intr = res["pesos"]
    section("1. Calidad: pesos (los del perfil personal sin estética ni color, renormalizados)")
    for k, v in glob.items():
        param(f"WG_{k.upper()}", f"Calidad global: peso {k}", v, "criterio", "config_mercado.yaml → calidad.pesos_origen ÷ 0,86")
    for k, v in intr.items():
        param(f"WI_{k.upper()}", f"Calidad intrínseca (sin precio ni coste de uso): peso {k}", v, "criterio", "config_mercado.yaml")
    q = cfg["calidad"]
    param("NEUTRO", "Puntuación neutra si falta el dato", q["neutro"], "criterio", "config_mercado.yaml")
    param("PRECIO_PEND", "Precio: puntos por unidad de descuento frente a la mediana (50 + d·k)", q["precio"]["pendiente"], "criterio")
    k = q["km_edad"]
    for nm, key in (("KM_MAX", "km_max"), ("ANIO_MIN", "anio_min"), ("KMA_IDEAL", "km_anio_ideal_max"), ("KMA_CERO", "km_anio_cero"),
                    ("W_KMT", "peso_km_total"), ("W_KMA", "peso_km_anio"), ("W_EDAD", "peso_edad")):
        param(nm, f"Km y edad: {key}", k[key], "criterio")
    param("SV_NCAP", "Seguridad: peso de Euro NCAP (estrellas/5·100)", q["seguridad_vial"]["peso_ncap"], "criterio")
    param("SV_ESP", "Seguridad: peso del ESP", q["seguridad_vial"]["peso_esp"], "criterio")
    param("GAR_FULL", "Seguridad de compra: meses de garantía para 100 puntos", q["seguridad_compra"]["garantia_meses_full"], "criterio")
    param("GAR_PRO", "Garantía legal de un profesional en usados (meses)", q["seguridad_compra"]["minimo_legal_profesional_meses"],
          "confirmado", "TRLGDCU art. 120 (ver fiscal.yaml → garantia_legal)")
    rf = res["refs"]
    param("USO_MIN", "Coste de uso anual con 100 puntos (percentil 10 de la muestra)", round(rf["USO_MIN"], 6), "calculado en Python", "percentil 10 del coste de uso")
    param("USO_MAX", "Coste de uso anual con 0 puntos (percentil 90 de la muestra)", round(rf["USO_MAX"], 6), "calculado en Python", "percentil 90")
    param("RV_N_FULL", "Reventa: nº de anuncios del modelo para 100 puntos de liquidez (percentil 90)", rf["RV_N_FULL"], "calculado en Python", "")
    table("ETQ_TBL", [[k2, v] for k2, v in res["etq_pts"].items()], ["Etiqueta", "Puntos (reventa)"], "config.yaml → scoring.etiqueta.puntos")

    section("2. Uso estándar y coste total de propiedad")
    u = cfg["uso"]
    param("KM_ANIO", "Km al año (uso estándar, mixto)", u["km_anio"], "supuesto configurable", "config_mercado.yaml → uso")
    param("ANIOS", "Años del cálculo", u["anios"], "supuesto configurable", "config_mercado.yaml → uso")
    param("ANIO_ACTUAL", "Año de referencia", res["anio_actual"], "dato", "fiscal.yaml")
    pe = sup["precio_energia"]
    table("ENER_TBL", [[f, pe[f]] for f in ("gasolina", "diesel", "hibrido", "phev", "glp", "gnc", "electrico")],
          ["Combustible", "€/l o €/kWh"], f"{pe['estado']} — {pe['fuente']}")
    c = ws.cell(r - 1, 2, "=VLOOKUP(ESCENARIO,REC_TBL,5,0)")      # electricidad: la del escenario de recarga (sección 2b)
    c.font = _font(GREEN)
    ws.cell(r - 1, 3, "electricidad: precio del escenario de recarga activo (ESCENARIO, sección 2b)")
    param("ENER_GASOLINA", "Precio de la energía si el combustible es desconocido (gasolina)", pe["gasolina"], pe["estado"], pe["fuente"])
    gp = sup["desfase_wltp_real"]
    table("GAP_TBL", [[f, gp[f]] for f in ("gasolina", "diesel", "hibrido", "glp", "gnc", "phev")], ["Combustible", "Desfase real/WLTP"],
          f"{gp['estado']} — {gp['fuente']}")
    cd = sup["consumo_por_defecto"]
    table("CONS_TBL", [[f"{f}|{s}", v] for f, d in cd.items() if isinstance(d, dict) for s, v in d.items()],
          ["Combustible|segmento", "Consumo real por defecto"], f"{cd['estado']} — {cd['fuente']}")
    sg = sup["seguro"]
    param("TR_HASTA", "Seguro: todo riesgo hasta N años; después terceros ampliado", sg["todo_riesgo_hasta_anios"], sg["estado"], sg["fuente"])
    table("TR_TBL", [[s, v] for s, v in sg["todo_riesgo"].items()], ["Segmento", "Todo riesgo €/año"], sg["estado"])
    table("TA_TBL", [[s, v] for s, v in sg["terceros_ampliado"].items()], ["Segmento", "Terceros ampliado €/año"], sg["estado"])
    param("TR_OTROS", "Todo riesgo, segmento sin tabla", sg["todo_riesgo"]["otros"], sg["estado"])
    param("TA_OTROS", "Terceros ampliado, segmento sin tabla", sg["terceros_ampliado"]["otros"], sg["estado"])
    mt = sup["mantenimiento_anual"]
    table("MANT_TBL", [[f, v] for f, v in mt.items() if isinstance(v, (int, float))], ["Combustible", "Mantenimiento €/año"],
          f"{mt['estado']} — {mt['fuente']}")
    param("MANT_GASOLINA", "Mantenimiento si el combustible es desconocido", mt["gasolina"], mt["estado"])
    ne = sup["neumaticos"]
    param("NEUM_KM", "Duración de un juego de neumáticos (km)", ne["duracion_km"], ne["estado"], ne["fuente"])
    table("NEUM_TBL", [[s, v] for s, v in ne["juego"].items()], ["Segmento", "Juego de 4 (€)"], ne["estado"])
    param("NEUM_OTROS", "Juego de neumáticos, segmento sin tabla", ne["juego"]["otros"], ne["estado"])
    iv = sup["ivtm"]
    desde = [0] + [h for h, _c in iv["tramos"][:-1]]
    table("IVTM_TBL", [[d, c] for d, (_h, c) in zip(desde, iv["tramos"])], ["CVF desde", "Cuota €/año"], f"{iv['estado']} — {iv['fuente']}")
    param("IVTM_SIN", "IVTM si no hay cilindrada", iv["cuota_sin_dato"], iv["estado"])
    table("IVTM_BON", [[f, v] for f, v in iv["bonificacion"].items()], ["Combustible", "Bonificación"], iv["estado"])
    ws.cell(r, 1, "Caballos fiscales: " + sup["cvf"]["formula"] + " — " + sup["cvf"]["cilindros"] + " — " + sup["cvf"]["fuente"])
    r += 1
    itp = fiscal["itp"]
    param("ITP_TIPO", "ITP tipo general (compra a particular)", itp["tipo"], itp["tipo_estado"], itp["tipo_fuente"])
    param("CUOTA_VALOR_MAX", "Cuota fija de ITP solo si el valor es menor de (€)", itp["cuota_fija_valor_max_eur"], itp["cuotas_fijas_estado"], itp["cuotas_fijas_fuente"])
    table("CF12", [[c["cc_min"], c["cc_max"] or 99999, c["cuota_eur"]] for c in itp["cuotas_fijas"] if c["antiguedad_mas_de_anios"] == 12],
          ["cc desde", "cc hasta", "Cuota fija (> 12 años)"], itp["cuotas_fijas_fuente"])
    param("TASA_DGT", "Tasa DGT de transferencia (usados)", fiscal["dgt"]["tasa_transferencia_eur"], fiscal["dgt"]["tasa_transferencia_estado"], fiscal["dgt"]["tasa_transferencia_fuente"])
    ws.cell(r, 1, "Coches nuevos y km 0: el impuesto de matriculación se supone incluido en el precio (" + sup["matriculacion"]["fuente"] + ")")
    r += 1

    section("2b. Eléctricos (recarga, batería) y vida útil restante")
    rc = sup["recarga"]
    param("ESCENARIO", "Escenario de recarga activo (casa / mixta / publica)", res["escenario_defecto"], "supuesto configurable",
          "config_mercado.yaml → recarga.escenario (la hoja Frontera muestra también los otros dos)")
    t0 = r + 1
    table("REC_P", [[m, rc["precios"][m]["eur_kwh"], rc["precios"][m]["fecha"], rc["precios"][m]["fuente"]] for m in ("casa", "publica_ac", "publica_dc")],
          ["Modo de recarga", "€/kWh (con impuestos)", "Fecha", "Fuente"])
    t1 = r + 1
    table("REC_TBL", [[e, w["casa"], w["publica_ac"], w["publica_dc"], None] for e, w in rc["escenarios"].items()],
          ["Escenario", "% casa", "% pública AC", "% pública DC", "€/kWh del escenario"], rc.get("fuente_reparto", ""))
    for rr in range(t1, r):
        c = ws.cell(rr, 5, f"=B{rr}*VLOOKUP(\"casa\",REC_P,2,0)+C{rr}*VLOOKUP(\"publica_ac\",REC_P,2,0)+D{rr}*VLOOKUP(\"publica_dc\",REC_P,2,0)")
        c.font = _font(GREEN)
    bt = sup["bateria"]
    so = bt["soh"]
    table("SOH_TBL", [[g, d["perdida_anual"], d["perdida_10k_km"], d.get("descripcion", "")] for g, d in so["grupos"].items()],
          ["Grupo de batería", "Pérdida de SOH por año", "Pérdida de SOH por 10.000 km", "Qué incluye"], f"{so['estado']} — {so['fuente']}")
    param("SOH_MIN", "SOH mínimo del modelo lineal (suelo)", so["minimo"], so["estado"], so["fuente"])
    e = res["electricos"]
    param("SOH_ELAST", "Elasticidad del valor residual al SOH (valor final × (SOH final / SOH hoy)^e)", e["elasticidad_valor_soh"],
          "supuesto configurable", "config_mercado.yaml → electricos")
    param("AUT_UMBRAL", "Autonomía real por debajo de la cual se penaliza la calidad (km)", e["autonomia_umbral_km"], "criterio configurable", "config_mercado.yaml → electricos")
    param("AUT_CERO", "Autonomía con la penalización máxima (km)", e["autonomia_penalizacion_max_km"], "criterio configurable", "config_mercado.yaml → electricos")
    param("AUT_PEN_MAX", "Penalización máxima de calidad por autonomía (puntos)", e["penalizacion_max_puntos"], "criterio configurable", "config_mercado.yaml → electricos")
    param("AUT_FACTOR", "Autonomía real / WLTP (solo informativo: ya aplicado en la columna 'Autonomía nueva')", bt["autonomia_wltp"]["factor_real"],
          bt["autonomia_wltp"]["estado"], bt["autonomia_wltp"]["fuente"])
    al = bt["alquiler"]
    param("BAT_CUOTA", "Cuota mensual del alquiler de batería (€/mes) si es de alquiler o no consta", al["cuota_mensual_eur"], al["estado"], al["fuente"])
    vu = sup["vida_util"]
    param("VIDA_ACTIVO", "Penalización por vida útil restante activa (1 = sí)", 1 if vu.get("activo", True) else 0, "supuesto configurable", "mercado_supuestos.yaml → vida_util")
    table("VIDA_TBL", [[k2, d["km"], d["anios"], d.get("nota", "")] for k2, d in vu["tabla"].items()],
          ["Combustible|segmento", "Vida útil (km)", "Vida útil (años)", "Nota"], f"{vu['estado']} — {vu['fuente']}")

    section("3. Depreciación estimada con los propios datos (factor que conserva a 5 años)")
    rows = []
    for key, d in res["dep"].items():
        rows.append([key, d["factor5"], d["b_edad"], d["se_edad"], d["b_km10k"], d["se_km10k"], d["n"], d["modelos"], d["r2_within"]])
    table("DEP_TBL", rows, ["Clave segmento|combustible", "Factor 5 años", "b edad", "EE edad", "b km/10.000", "EE km", "n", "modelos", "R² within"],
          "calculado en Python: log(precio) = FE(modelo) + b_edad·edad + b_km·km/10.000; factor = exp(5·b_edad + 5·KM_ANIO/10.000·b_km)")
    cd2 = sup.get("contraste_depreciacion") or {}
    ws.cell(r, 1, "Contraste publicado: GANVAM-DAT valor residual a 3 años " + str(cd2.get("ganvam_dat_valor_residual_3_anios")) +
            " · OCU/BEUC pérdida a 3 años " + str(cd2.get("ocu_beuc_perdida_3_anios")))
    r += 1
    for col, wdt in zip("ABCDEFGHIJ", [52, 16, 22, 40, 14, 12, 10, 10, 10, 40]):
        ws.column_dimensions[col].width = wdt


# ------------------------------------------------------------------ Anuncios
COLUMNS = [
    ("uid", "ID", "data", None), ("plataforma", "Plataforma", "data", None), ("zona", "Zona", "data", None),
    ("tipo", "Tipo de anuncio", "data", None), ("marca", "Marca", "data", None), ("modelo_key", "Modelo", "data", None),
    ("titulo", "Título", "data", None), ("anio", "Año", "data", None), ("km", "Km", "data", None), ("precio", "Precio al contado (€)", "data", None),
    ("combustible", "Combustible", "data", None), ("cambio", "Cambio", "data", None), ("cv", "Potencia (CV)", "data", None),
    ("cc_est", "Cilindrada (cc)", "data", None), ("segmento", "Segmento", "data", None), ("etiqueta", "Etiqueta", "data", None),
    ("etq_fuente", "Fuente etiqueta", "data", None), ("vendedor", "Vendedor", "data", None), ("gar_anuncio", "Garantía del anuncio (meses)", "data", None),
    ("consumo_wltp", "Consumo WLTP del anuncio (l/100)", "data", None), ("ncap", "Euro NCAP (estrellas)", "data", None),
    ("ncap_vig", "Euro NCAP vigente", "data", None), ("ncap_asist", "Ayudas a la conducción (Euro NCAP, % safety assist)", "data", None),
    ("esp", "ESP", "data", None), ("fiab", "Fiabilidad (0-100)", "data", None),
    ("mediana", "Mediana de mercado (€)", "data", None), ("nivel_med", "Nivel de la mediana", "data", None),
    ("n_modelo", "Anuncios del modelo", "data", None), ("dep_clave", "Clave de depreciación", "data", None),
    ("soh_grupo", "Grupo de batería (SOH)", "data", None), ("aut_nueva", "Autonomía real con batería nueva (km)", "data", None),
    ("bat_estado", "Batería (propiedad / alquiler / no consta)", "data", None), ("vida_clave", "Clave de vida útil", "data", None),
    ("url", "Enlace", "data", None),
    # ---- coste total de propiedad
    ("edad", "Edad (años)", "calc", "=MAX(0,ANIO_ACTUAL-{anio})"),
    ("cons", "Consumo real (l o kWh/100 km)", "calc",
     '=IF(AND(N({consumo_wltp})>0,{combustible}<>"electrico"),{consumo_wltp}*(1+IFERROR(VLOOKUP({combustible},GAP_TBL,2,0),0)),'
     'IFERROR(VLOOKUP({combustible}&"|"&{segmento},CONS_TBL,2,0),IFERROR(VLOOKUP({combustible}&"|otros",CONS_TBL,2,0),0)))'),
    ("p_ener", "Precio energía", "calc", "=IFERROR(VLOOKUP({combustible},ENER_TBL,2,0),ENER_GASOLINA)"),
    ("energia", "Energía €/año", "calc", "={cons}*KM_ANIO/100*{p_ener}"),
    ("seguro", "Seguro €/año", "calc",
     "=IF({edad}<=TR_HASTA,IFERROR(VLOOKUP({segmento},TR_TBL,2,0),TR_OTROS),IFERROR(VLOOKUP({segmento},TA_TBL,2,0),TA_OTROS))"),
    ("mant", "Mantenimiento €/año", "calc", "=IFERROR(VLOOKUP({combustible},MANT_TBL,2,0),MANT_GASOLINA)"),
    ("neum", "Neumáticos €/año", "calc", "=KM_ANIO/NEUM_KM*IFERROR(VLOOKUP({segmento},NEUM_TBL,2,0),NEUM_OTROS)"),
    ("ncil", "Cilindros (estimados)", "calc", '=IF(N({cc_est})=0,"",IF({cc_est}<1100,3,IF({cc_est}<2600,4,IF({cc_est}<3600,6,8))))'),
    ("cvf", "Caballos fiscales", "calc",
     '=IF({combustible}="electrico",IF(N({cv})>0,{cv}*0.7355/5.152,""),IF(N({cc_est})>0,0.08*({cc_est}/{ncil})^0.6*{ncil},""))'),
    ("ivtm", "IVTM €/año", "calc",
     '=IF({cvf}="",IVTM_SIN,VLOOKUP({cvf},IVTM_TBL,2,1))*(1-IFERROR(VLOOKUP({combustible},IVTM_BON,2,0),0))'),
    ("itp", "ITP (€)", "calc",
     '=IF(OR({vendedor}<>"particular",{tipo}="nuevo",{tipo}="km0"),0,IF(AND({edad}>12,{precio}<CUOTA_VALOR_MAX),'
     'SUMPRODUCT((INDEX(CF12,0,1)<=IF(N({cc_est})>0,{cc_est},99999))*(INDEX(CF12,0,2)>=IF(N({cc_est})>0,{cc_est},99999))*INDEX(CF12,0,3)),'
     '{precio}*ITP_TIPO))'),
    ("tasa", "Tasa DGT (€)", "calc", '=IF(OR({tipo}="nuevo",{tipo}="km0"),0,TASA_DGT)'),
    ("dep_f", "Factor de valor a 5 años", "calc", "=VLOOKUP({dep_clave},DEP_TBL,2,0)"),
    ("soh", "SOH batería hoy", "calc",
     '=IF({soh_grupo}="","",MAX(SOH_MIN,1-VLOOKUP({soh_grupo},SOH_TBL,2,0)*{edad}-VLOOKUP({soh_grupo},SOH_TBL,3,0)*{km}/10000))'),
    ("soh_fin", "SOH batería al final", "calc",
     '=IF({soh_grupo}="","",MAX(SOH_MIN,1-VLOOKUP({soh_grupo},SOH_TBL,2,0)*({edad}+ANIOS)-VLOOKUP({soh_grupo},SOH_TBL,3,0)*({km}+ANIOS*KM_ANIO)/10000))'),
    ("autonomia", "Autonomía real estimada hoy (km)", "calc", '=IF(OR({soh}="",N({aut_nueva})=0),"",{aut_nueva}*{soh})'),
    ("pen_aut", "Penalización por autonomía (puntos)", "calc",
     '=IF({autonomia}="",0,AUT_PEN_MAX*MAX(0,MIN(1,(AUT_UMBRAL-{autonomia})/(AUT_UMBRAL-AUT_CERO))))'),
    ("deprec_mkt", "Depreciación de mercado 5 años (€)", "calc", '={precio}*(1-{dep_f}*IF({soh}="",1,({soh_fin}/{soh})^SOH_ELAST))'),
    ("frac_vida", "Vida útil restante que se consume", "calc",
     "=MIN(1,MAX(ANIOS*KM_ANIO/MAX(VLOOKUP({vida_clave},VIDA_TBL,2,0)-{km},1),ANIOS/MAX(VLOOKUP({vida_clave},VIDA_TBL,3,0)-{edad},0.1)))"),
    ("deprec", "Depreciación 5 años (€)", "calc", "=IF(VIDA_ACTIVO=1,MAX({deprec_mkt},{precio}*{frac_vida}),{deprec_mkt})"),
    ("cuota_bat", "Alquiler de batería €/año", "calc", '=IF(OR({bat_estado}="alquiler",{bat_estado}="no consta"),12*BAT_CUOTA,0)'),
    ("uso_anual", "Coste de uso €/año", "calc", "={energia}+{seguro}+{mant}+{neum}+{ivtm}+{cuota_bat}"),
    ("tco", "COSTE TOTAL 5 AÑOS (€)", "calc", "={itp}+{tasa}+{deprec}+ANIOS*{uso_anual}"),
    ("coste_anual", "Coste anual (€)", "calc", "={tco}/ANIOS"),
    # ---- calidad
    ("s_fiab", "P. Fiabilidad", "calc", "={fiab}"),
    ("s_precio", "P. Precio", "calc", '=IF({mediana}="",50,MAX(0,MIN(100,50+({mediana}-{precio})/{mediana}*PRECIO_PEND)))'),
    ("s_estado", "P. Estado", "calc", '=IF(OR({tipo}="nuevo",{tipo}="km0"),100,NEUTRO)'),
    ("s_segvial", "P. Seguridad", "calc",
     '=SV_NCAP*IF({ncap}="",NEUTRO,{ncap}/5*100)+SV_ESP*IF({esp}="sí",100,IF({esp}="no",0,NEUTRO))'),
    ("gar_ef", "Garantía efectiva (meses)", "calc",
     '=IF(N({gar_anuncio})>0,{gar_anuncio},IF(OR({tipo}="nuevo",{tipo}="km0"),36,IF({vendedor}="profesional",GAR_PRO,0)))'),
    ("s_compra", "P. Seguridad de compra", "calc", "=100*MIN(1,{gar_ef}/GAR_FULL)"),
    ("s_uso", "P. Coste de uso", "calc", "=MAX(0,MIN(100,100*(USO_MAX-{uso_anual})/(USO_MAX-USO_MIN)))"),
    ("kma", "Km/año", "calc", "={km}/MAX({edad},0.5)"),
    ("s_kmedad", "P. Km y edad", "calc",
     "=W_KMT*MAX(0,100*(1-{km}/KM_MAX))+W_KMA*IF({kma}<=KMA_IDEAL,100,MAX(0,100*(KMA_CERO-{kma})/(KMA_CERO-KMA_IDEAL)))"
     "+W_EDAD*MAX(0,MIN(100,100*({anio}-ANIO_MIN)/(ANIO_ACTUAL-ANIO_MIN)))"),
    ("s_reventa", "P. Reventa", "calc",
     '=0.5*MAX(0,MIN(100,100*{n_modelo}/RV_N_FULL))+0.5*IF({etiqueta}="",0,IFERROR(VLOOKUP({etiqueta},ETQ_TBL,2,0),0))'),
    ("calidad", "CALIDAD GLOBAL", "calc",
     "=MAX(0,WG_FIABILIDAD*{s_fiab}+WG_PRECIO*{s_precio}+WG_ESTADO*{s_estado}+WG_SEGURIDAD_VIAL*{s_segvial}+WG_SEGURIDAD_COMPRA*{s_compra}"
     "+WG_COSTE_USO*{s_uso}+WG_KM_EDAD*{s_kmedad}+WG_REVENTA*{s_reventa}-{pen_aut})"),
    ("calidad_intr", "Calidad intrínseca", "calc",
     "=MAX(0,WI_FIABILIDAD*{s_fiab}+WI_ESTADO*{s_estado}+WI_SEGURIDAD_VIAL*{s_segvial}+WI_SEGURIDAD_COMPRA*{s_compra}"
     "+WI_KM_EDAD*{s_kmedad}+WI_REVENTA*{s_reventa}-{pen_aut})"),
    ("ratio", "Calidad / coste anual (por 1.000 €)", "calc", "=IF({coste_anual}>0,{calidad_intr}/({coste_anual}/1000),0)"),
    ("franja", "Franja de precio", "calc",
     '=IF({precio}<5000,"0-5000",IF({precio}<10000,"5000-10000",IF({precio}<15000,"10000-15000",IF({precio}<25000,"15000-25000",">25000"))))'),
]
COL = {k: get_column_letter(i) for i, (k, *_r) in enumerate(COLUMNS, 1)}

# Columna -> valor esperado en Python (tests y tools/verify_mercado.py)
CHECKS = {"edad": lambda a: a["edad"], "cons": lambda a: a["consumo"] or 0, "energia": lambda a: a["energia"],
          "seguro": lambda a: a["seguro"], "mant": lambda a: a["mant"], "neum": lambda a: a["neum"], "ivtm": lambda a: a["ivtm"],
          "itp": lambda a: a["itp"], "deprec": lambda a: a["depreciacion"], "soh": lambda a: a["soh"], "soh_fin": lambda a: a["soh_fin"],
          "autonomia": lambda a: a["autonomia"], "pen_aut": lambda a: a["pen_aut"], "deprec_mkt": lambda a: a["deprec_mkt"],
          "frac_vida": lambda a: a["frac_vida"], "cuota_bat": lambda a: a["cuota_bat"], "uso_anual": lambda a: a["uso_anual"],
          "tco": lambda a: a["tco"], "coste_anual": lambda a: a["coste_anual"], "s_precio": lambda a: a["s"]["precio"],
          "s_segvial": lambda a: a["s"]["seguridad_vial"], "s_compra": lambda a: a["s"]["seguridad_compra"],
          "s_uso": lambda a: a["s"]["coste_uso"], "s_kmedad": lambda a: a["s"]["km_edad"], "s_reventa": lambda a: a["s"]["reventa"],
          "calidad": lambda a: a["calidad"], "calidad_intr": lambda a: a["calidad_intr"], "ratio": lambda a: a["ratio"],
          "franja": lambda a: a["franja"]}

NOTES = {
    "uid": "Datos de los listados de cada plataforma (azul). Fuente exacta: columna Enlace y fichero de raw/ guardado.",
    "precio": "Precio al contado del listado (OcasionPlus y Flexicar dan contado y financiado; se usa el contado).",
    "tipo": "nuevo / km0 / ocasión según la plataforma; 'seminuevo' = ocasión con <= 2 años y <= 30.000 km (config_mercado.yaml).",
    "cc_est": "Cilindrada del anuncio o, si no la trae, la del título (litros) o un supuesto por segmento (mercado_supuestos.yaml).",
    "fiab": "Calculado en Python (src/mercado/analysis.py): media de TÜV 2026 de la franja de edad del coche, TÜV de la generación "
            "(reliability.yaml) y OCU 2026 de la marca, más los ajustes por motor documentados. Sin dato: NEUTRO.",
    "ncap": "Estrellas Euro NCAP de la generación (reliability.yaml → euroncap y mercado_fiabilidad.yaml). Fuente en la nota de cada celda.",
    "mediana": "Calculada en Python con todos los anuncios limpios (modelo+año+km de 25.000 en 25.000 → modelo+año → modelo+3 años; mín. 5).",
    "dep_clave": "Clave de la tabla DEP_TBL (Supuestos) con la depreciación estimada para su segmento y combustible.",
    "soh_grupo": "Solo eléctricos: grupo de degradación de la batería (refrigeración líquida, por aire…) según el modelo y la generación "
                 "(mercado_supuestos.yaml → bateria.soh, con fuentes). Tabla SOH_TBL en Supuestos.",
    "aut_nueva": "Solo eléctricos: autonomía WLTP de la versión (por año y, si el título da los kWh, la capacidad más cercana) × AUT_FACTOR "
                 "(real/WLTP). Fuente de cada celda en su nota. Vacío = PENDIENTE (modelo sin dato).",
    "bat_estado": "Solo modelos vendidos con batería en alquiler (Renault ZE…): 'alquiler' o 'propiedad' si el título lo dice; si no, "
                  "'no consta' y se suma la cuota (criterio prudente). A nivel de listado no hay descripción completa.",
    "vida_clave": "Clave de VIDA_TBL (Supuestos): vida útil esperada por combustible y segmento.",
    "etiqueta": "Etiqueta del anuncio o, si no la trae, la regla de la DGT por combustible y año (la peor posible).",
}


def _expand(tpl: str, r: int) -> str:
    return re.sub(r"\{([a-z_0-9]+)\}", lambda m: f"{COL[m.group(1)]}{r}", tpl)


def row_data(a: dict) -> dict:
    return {"uid": a["uid"], "plataforma": a["plataforma"], "zona": a["zona"], "tipo": a["tipo_m"], "marca": a["marca"],
            "modelo_key": a["modelo_key"], "titulo": a.get("titulo"), "anio": a["anio"], "km": a["km"], "precio": a["precio"],
            "combustible": a["combustible"], "cambio": a["cambio"], "cv": a.get("cv"), "cc_est": a["cc_est"], "segmento": a["segmento"],
            "etiqueta": a["etiqueta"], "etq_fuente": a.get("etiqueta_fuente"), "vendedor": a.get("vendedor"),
            "gar_anuncio": a.get("garantia_meses"), "consumo_wltp": a.get("consumo_wltp"), "ncap": a["ncap"], "ncap_vig": a["ncap_vigencia"] or None, "ncap_asist": a.get("ncap_asist"),
            "esp": a["esp"], "fiab": a["fiab"], "mediana": a["mediana"], "nivel_med": a["nivel_mediana"] or None,
            "n_modelo": a["n_modelo"], "dep_clave": a["dep_clave"], "soh_grupo": a.get("soh_grupo"),
            "aut_nueva": round(a["aut_nueva"], 6) if a.get("aut_nueva") else None, "bat_estado": a.get("bat_estado"),
            "vida_clave": a["vida_clave"], "url": a.get("url")}


def build_anuncios(wb, ads: list[dict], names: Names) -> int:
    ws = wb.create_sheet("Anuncios", 0)
    for i, (key, hdr, kind, _t) in enumerate(COLUMNS, 1):
        c = ws.cell(1, i, hdr)
        c.font = Font(bold=True)
        c.fill = HDR_FILL
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if key in NOTES:
            c.comment = Comment(NOTES[key], "mercado")
    # color de cada columna calculada (constante por columna): verde si usa nombres de Supuestos
    verde = {k: _font(GREEN if any(re.search(rf"(?<![A-Za-z_]){n}(?![A-Za-z_0-9])", t) for n in names.names) else BLACK)
             for k, _h, kind, t in COLUMNS if kind != "data"}
    for r, a in enumerate(ads, 2):
        d = row_data(a)
        for i, (key, _h, kind, tpl) in enumerate(COLUMNS, 1):
            cell = ws.cell(r, i)
            if kind == "data":
                cell.value = d[key]
                cell.font = _font(BLUE)
                if key == "ncap" and a.get("ncap_ref"):
                    cell.comment = Comment(a["ncap_ref"], "mercado")
                if key == "fiab":
                    cell.comment = Comment(a["fiab_fuente"], "mercado")
                if key == "aut_nueva" and a.get("aut_fuente"):
                    cell.comment = Comment(a["aut_fuente"], "mercado")
            else:
                f = _expand(tpl, r)
                cell.value = f
                cell.font = verde[key]
    for key, col in COL.items():
        ws.column_dimensions[col].width = {"titulo": 38, "url": 30, "modelo_key": 22}.get(key, 12)
    return len(ads) + 1


def _rng(key, n_last):
    return f"Anuncios!${COL[key]}$2:${COL[key]}${n_last}"


# ------------------------------------------------------------------ resto de hojas
def hdr(ws, r, cols):
    for i, h in enumerate(cols, 1):
        c = ws.cell(r, i, h)
        c.font = Font(bold=True)
        c.fill = HDR_FILL
        c.alignment = Alignment(wrap_text=True, vertical="top")


def build_precios(wb, res, n_last):
    ws = wb.create_sheet("Precios por modelo")
    ws.cell(1, 1, "Precio por modelo, generación, año y km (anuncios limpios de la zona base, Valencia; Madrid y Barcelona como referencia)").font = SEC_FONT
    ws.cell(2, 1, "Azul: calculado en Python con la hoja Anuncios. Verde (nivel 'modelo'): la misma mediana y el mismo número con "
                  "fórmulas sobre Anuncios, para comprobarlo.")
    hdr(ws, 4, ["Nivel", "Grupo", "N anuncios", "Mediana (€)", "P25 (€)", "P75 (€)", "N (fórmula)", "Mediana (fórmula)"])
    r = 5
    for p in res["precios"]:
        ws.cell(r, 1, p["nivel"])
        ws.cell(r, 2, p["grupo"]).font = _font(BLUE)
        for i, k in enumerate(("n", "mediana", "p25", "p75"), 3):
            c = ws.cell(r, i, p[k])
            c.font = _font(BLUE)
            c.number_format = "#,##0"
        if p["nivel"] == "modelo":
            ws.cell(r, 7, f'=COUNTIFS({_rng("modelo_key", n_last)},B{r},{_rng("zona", n_last)},"valencia")').font = _font(GREEN)
            ws.cell(r, 8).value = ArrayFormula(f"H{r}", f'=MEDIAN(IF(({_rng("modelo_key", n_last)}=B{r})*({_rng("zona", n_last)}="valencia"),{_rng("precio", n_last)}))')
            ws.cell(r, 8).font = _font(GREEN)
        r += 1
    for col, w in zip("ABCDEFGH", [30, 52, 11, 12, 12, 12, 12, 14]):
        ws.column_dimensions[col].width = w


def build_depreciacion(wb, res):
    ws = wb.create_sheet("Depreciación")
    ws.cell(1, 1, "Curvas de depreciación estimadas con los propios datos (valor frente a edad y km)").font = SEC_FONT
    ws.cell(2, 1, "Modelo: log(precio) = efectos fijos de modelo + b_edad·edad + b_km·km/10.000 (MCO within, errores HC1). "
                  "Valor relativo a la edad a con KM_ANIO km/año = exp(b_edad·a + b_km·a·KM_ANIO/10.000). Azul: coeficientes de Python; "
                  "negro: curva calculada en la hoja.")
    edades = list(range(0, 13))
    hdr(ws, 4, ["Grupo", "n", "Modelos", "b edad", "EE edad", "b km/10.000", "EE km", "R² within", "Pérdida anual (%)"] + [f"{a} años" for a in edades])
    r = 5
    for d in res["curvas_seg"] + res["curvas_marca"]:
        vals = [d["grupo"], d["n"], d["modelos"], d["b_edad"], d["se_edad"], d["b_km10k"], d["se_km10k"], d["r2_within"]]
        for i, v in enumerate(vals, 1):
            ws.cell(r, i, v).font = _font(BLUE)
        ws.cell(r, 9, f"=EXP(D{r}+F{r}*KM_ANIO/10000)-1").font = _font(GREEN)
        ws.cell(r, 9).number_format = "0.0%"
        for j, a in enumerate(edades):
            c = ws.cell(r, 10 + j, f"=EXP(D{r}*{a}+F{r}*{a}*KM_ANIO/10000)")
            c.font = _font(GREEN)
            c.number_format = "0%"
        r += 1
    ws.column_dimensions["A"].width = 30


def build_oferta(wb, res, n_last):
    ws = wb.create_sheet("Oferta")
    ws.cell(1, 1, "Oferta: volumen de anuncios limpios por dimensión (todas las zonas), y precio mediano en Valencia").font = SEC_FONT
    r = 3
    for dim, col in (("segmento", "segmento"), ("combustible", "combustible"), ("etiqueta", "etiqueta"), ("franja", "franja"),
                     ("tipo_m", "tipo"), ("zona", "zona"), ("plataforma", "plataforma")):
        hdr(ws, r, [f"{dim}", "Anuncios (Python)", "Anuncios (fórmula)", "Precio mediano Valencia (€)"])
        r += 1
        for k, n in res["oferta"][dim].most_common():
            ws.cell(r, 1, k).font = _font(BLUE)
            ws.cell(r, 2, n).font = _font(BLUE)
            ws.cell(r, 3, f'=COUNTIFS({_rng(col, n_last)},"="&A{r})' if k != "sin dato" else f'=COUNTBLANK({_rng(col, n_last)})').font = _font(GREEN)
            md = (res["med_seg"].get(dim) or {}).get(k)
            if md:
                c = ws.cell(r, 4, md[1])
                c.font = _font(BLUE)
                c.number_format = "#,##0"
            r += 1
        r += 1
    liq = res["liquidez"].get("todos") or []
    ws.cell(r, 1, "Liquidez: días hasta que desaparece el anuncio").font = SEC_FONT
    r += 1
    ws.cell(r, 1, f"Anuncios desaparecidos observados: {len(liq)}" + ("" if liq else
            " — hace falta ejecutar run_mercado.py varios días (p. ej. con --watch): un anuncio se da por vendido tras 2 recorridos completos sin verlo."))
    for col, w in zip("ABCD", [28, 16, 16, 22]):
        ws.column_dimensions[col].width = w


PRIMAS = ("Etiqueta C frente a B", "Etiqueta ECO frente a C", "Cambio automático frente a manual")


def build_primas(wb, res):
    ws = wb.create_sheet("Primas")
    pr = res["primas"]
    ws.cell(1, 1, "Primas de precio por etiqueta y por cambio automático: especificación nueva (FE de marca, errores agrupados por "
                  "modelo) frente a la anterior (FE de modelo, errores HC1)").font = SEC_FONT
    r = 3
    for sk, titulo in (("marca_cl", "NUEVA (principal)"), ("modelo_cl", "Robustez"), ("anterior", "ANTERIOR")):
        m = pr.get(sk)
        if not m:
            ws.cell(r, 1, f"{titulo}: sin datos suficientes")
            r += 2
            continue
        ws.cell(r, 1, f"{titulo} — {m['descripcion']}").font = Font(bold=True)
        r += 1
        ws.cell(r, 1, "Especificación: " + m["especificacion"])
        r += 1
        ws.cell(r, 1, f"n = {m['n']} anuncios · {m['grupos']} grupos de efectos fijos · "
                      f"{m['clusters'] or '—'} clústeres · {m['k']} regresores · R² within = {m['r2_within']:.3f}")
        r += 1
        hdr(ws, r, ["Prima", "Coeficiente (log)", f"Error estándar ({m['errores']})", "Prima (%)", "IC 95 % inferior", "IC 95 % superior",
                    "Anuncios con el atributo"])
        r += 1
        for lab in PRIMAS:
            d = m.get(lab)
            if not d:
                ws.cell(r, 1, lab)
                ws.cell(r, 2, "sin datos suficientes")
                r += 1
                continue
            for i, v in enumerate([lab, d["b"], d["se"], d["pct"], d["lo"], d["hi"], d["n_con"]], 1):
                c = ws.cell(r, i, v)
                c.font = _font(BLUE)
                if 4 <= i <= 6:
                    c.number_format = "0.0%"
            r += 1
        r += 1
    # comparación compacta
    ws.cell(r, 1, "Comparación (prima % [IC 95 %])").font = SEC_FONT
    r += 1
    hdr(ws, r, ["Prima", "Anterior: FE modelo + HC1", "FE modelo + agrupados", "Nueva: FE marca + agrupados"])
    r += 1
    for lab in PRIMAS:
        ws.cell(r, 1, lab)
        for j, sk in enumerate(("anterior", "modelo_cl", "marca_cl"), 2):
            d = (pr.get(sk) or {}).get(lab)
            ws.cell(r, j, f"{d['pct'] * 100:+.1f} % [{d['lo'] * 100:+.1f} ; {d['hi'] * 100:+.1f}]" if d else "—").font = _font(BLUE)
        r += 1
    r += 1
    for t in ("Lectura: prima (%) = exp(coeficiente) − 1. IC 95 % = exp(coef ± 1,96·EE) − 1.",
              "Errores agrupados por modelo (CR1): admiten que los anuncios de un mismo modelo estén correlacionados (mismo vendedor, "
              "misma tarifa, mismas versiones); suelen ser más anchos que HC1, que trata cada anuncio como independiente.",
              "Con FE de modelo la prima se identifica DENTRO de cada modelo (efecto fijo de marca absorbido: la marca no varía dentro "
              "de un modelo). Con FE de marca (más segmento) se compara entre modelos de la misma marca: usa más variación, pero mezcla "
              "la etiqueta o el cambio con diferencias entre modelos que no recogen los controles.",
              "ECO frente a C = coef(ECO) − coef(C), con su varianza (incluida la covarianza) de la misma matriz robusta.",
              "Muestra: anuncios de ocasión y seminuevos con etiqueta, cambio y combustible conocidos (en Coches.net el cambio solo consta si el título lo dice)."):
        ws.cell(r, 1, t)
        r += 1
    r += 1
    ws.cell(r, 1, "Modelo de valor para detectar infravalorados").font = SEC_FONT
    r += 1
    for lab, ri in (("Nueva", res["reg_infra"]), ("Anterior", res["reg_infra_ant"])):
        ws.cell(r, 1, f"{lab}: " + ri["especificacion"] + f" · n = {ri['n']} · R² = {ri['r2']:.3f} · b(calidad intrínseca) = "
                f"{ri['b_calidad'][0]:.4f} (EE {ri['b_calidad'][1]:.4f})")
        r += 1
    for col, w in zip("ABCDEFG", [40, 26, 26, 28, 14, 14, 18]):
        ws.column_dimensions[col].width = w


def build_sensibilidad(wb, res):
    ws = wb.create_sheet("Sensibilidad")
    sn = res["sensibilidad"]
    ix = {a["uid"]: a for a in res["base_ads"]}

    def nom(u):
        a = ix[u]
        return f"{a['titulo'] or a['modelo_key']} ({a['anio']}, {a['km']:,} km, {a['precio']:,.0f} €)".replace(",", ".")
    ws.cell(1, 1, f"Sensibilidad del Top 5 por franja (calidad intrínseca / coste anual) a ±{int(sn['variacion'] * 100)} % en el precio de "
                  "la energía, el seguro y la depreciación (Valencia; escenario de recarga " + res["escenario_defecto"] + ")").font = SEC_FONT
    ws.cell(2, 1, "Azul: calculado en Python (src/mercado/analysis.py) moviendo un componente cada vez sobre el coste anual de la hoja "
                  "Anuncios; la calidad no cambia. 'Cambios' = coches que entran en el Top 5 respecto al caso base.")
    r = 4
    casos = list(sn["casos"])
    for f in FRANJAS:
        ws.cell(r, 1, f"Franja {f} €").font = Font(bold=True)
        r += 1
        hdr(ws, r, ["Caso", "Cambios"] + [f"Puesto {i}" for i in range(1, 6)])
        r += 1
        ws.cell(r, 1, "Base")
        ws.cell(r, 2, 0).font = _font(BLUE)
        for j, u in enumerate(sn["base"][f], 3):
            ws.cell(r, j, nom(u)).font = _font(BLUE)
        r += 1
        for cs in casos:
            d = sn["casos"][cs][f]
            ws.cell(r, 1, cs)
            ws.cell(r, 2, len(d["entran"])).font = _font(BLUE)
            for j, u in enumerate(d["uids"], 3):
                c = ws.cell(r, j, ("▲ " if u in d["entran"] else "") + nom(u))
                c.font = _font(BLUE)
            r += 1
        r += 1
    for col, w in zip("ABCDEFG", [22, 9, 44, 44, 44, 44, 44]):
        ws.column_dimensions[col].width = w


def _fila_listado(ws, r, a, n_last, rank=None):
    """Fila de un coche: ID en azul y el resto traído de Anuncios con INDEX/MATCH (verde)."""
    ws.cell(r, 1, rank).font = _font(BLUE)
    ws.cell(r, 2, a["uid"]).font = _font(BLUE)
    m = f"MATCH($B{r},{_rng('uid', n_last)},0)"
    for j, key in enumerate(("titulo", "anio", "km", "precio", "coste_anual", "calidad_intr", "ratio", "segmento", "combustible", "url"), 3):
        c = ws.cell(r, j, f"=INDEX({_rng(key, n_last)},{m})")
        c.font = _font(GREEN)
        if key in ("precio", "coste_anual", "km"):
            c.number_format = "#,##0"
        if key in ("calidad_intr", "ratio"):
            c.number_format = "0.0"
    if a.get("url"):
        ws.cell(r, 12).hyperlink = a["url"]


LIST_HDR = ["Nº", "ID", "Coche", "Año", "Km", "Precio (€)", "Coste anual (€)", "Calidad intrínseca", "Calidad / coste (por 1.000 €)",
            "Segmento", "Combustible", "Enlace"]


def build_frontera(wb, res, n_last):
    ws = wb.create_sheet("Frontera")
    ws.cell(1, 1, "Frontera eficiente calidad intrínseca frente a coste anual (Valencia). Un coche es eficiente si ningún otro de su "
                  "franja cuesta lo mismo o menos al año con más calidad.").font = SEC_FONT
    r = 3
    chart_rows = []
    for f in FRANJAS:
        lst = res["frontera"].get(f) or []
        ws.cell(r, 1, f"Franja {f} € — {len(lst)} coches eficientes").font = Font(bold=True)
        r += 1
        hdr(ws, r, LIST_HDR)
        r += 1
        r0 = r
        for i, a in enumerate(lst, 1):
            _fila_listado(ws, r, a, n_last, i)
            r += 1
        if lst:
            chart_rows.append((f, r0, r - 1))
        r += 1
    ix = {a["uid"]: a for a in res["base_ads"]}
    ws.cell(r, 1, "Escenarios de recarga (solo cambia la energía de los eléctricos; la lista de arriba es el escenario activo, "
                  f"'{res['escenario_defecto']}', con fórmulas). Azul: calculado en Python.").font = SEC_FONT
    r += 1
    hdr(ws, r, ["Escenario", "€/kWh", "Franja", "Coches eficientes", "Coches de la frontera (de menor a mayor coste anual)", "", "Top 5 calidad/coste"])
    r += 1
    for e, d in res["escenarios"].items():
        for f in FRANJAS:
            lst = d["frontera"].get(f) or []
            vals = [e + (" (activo)" if d["defecto"] else ""), d["precio"], f, len(lst),
                    " · ".join(f"{a['titulo'] or a['modelo_key']} {a['anio']} ({d['coste'](a):,.0f} €/año)".replace(",", ".") for a in lst), "",
                    " · ".join(f"{a['titulo'] or a['modelo_key']} {a['anio']}" for a in d["top"][f])]
            for j, v in enumerate(vals, 1):
                c = ws.cell(r, j, v)
                c.font = _font(BLUE)
            ws.cell(r, 2).number_format = "0.000"
            r += 1
    ch = ScatterChart()
    ch.title = "Frontera eficiente por franja de precio (Valencia)"
    ch.x_axis.title = "Coste anual (€)"
    ch.y_axis.title = "Calidad intrínseca"
    ch.style = 13
    for f, a, b in chart_rows:
        s = Series(Reference(ws, min_col=8, min_row=a, max_row=b), Reference(ws, min_col=7, min_row=a, max_row=b), title=f"{f} €")
        s.marker.symbol = "circle"
        s.graphicalProperties.line.noFill = False
        ch.series.append(s)
    ch.height, ch.width = 12, 22
    ws.add_chart(ch, "N3")
    for col, w in zip("ABCDEFGHIJKL", [5, 18, 40, 7, 10, 11, 12, 12, 14, 12, 12, 40]):
        ws.column_dimensions[col].width = w


def build_top(wb, res, n_last):
    ws = wb.create_sheet("Top por franja")
    r = 1
    ws.cell(r, 1, "Top 5 por calidad intrínseca / coste anual (Valencia)").font = SEC_FONT
    r += 2
    for titulo, grupos in (("Por franja de precio", res["top_franja"]), ("Por segmento", res["top_segmento"])):
        ws.cell(r, 1, titulo).font = SEC_FONT
        r += 1
        for g, lst in grupos.items():
            ws.cell(r, 1, f"{g}").font = Font(bold=True)
            r += 1
            hdr(ws, r, LIST_HDR)
            r += 1
            for i, a in enumerate(lst, 1):
                _fila_listado(ws, r, a, n_last, i)
                r += 1
            r += 1
    ws.cell(r, 1, "Modelos infravalorados: cotizan por debajo de lo que predice el modelo de valor para su calidad, edad, km, "
                  "segmento, combustible y tipo (mediana del residuo del modelo; mín. 5 anuncios)").font = SEC_FONT
    r += 1
    ws.cell(r, 1, "Nueva especificación: efecto fijo de marca (se compara con modelos de su misma marca) y errores agrupados por modelo. "
                  "'Puesto anterior' = puesto con la especificación anterior (sin efectos fijos).")
    r += 1
    hdr(ws, r, ["Nº", "Modelo", "Anuncios", "Por debajo de lo previsto (%)", "Calidad intrínseca mediana", "Precio mediano (€)", "Segmento",
                "Puesto anterior"])
    r += 1
    for i, d in enumerate(res["infravalorados"][:20], 1):
        for j, v in enumerate([i, d["modelo"], d["n"], d["pct"], d["calidad_intr"], d["precio_mediano"], d["segmento"], d.get("pos_ant")], 1):
            c = ws.cell(r, j, v)
            c.font = _font(BLUE)
            if j == 4:
                c.number_format = "0.0%"
        r += 1
    r += 1
    ws.cell(r, 1, "Especificación anterior (sin efectos fijos, errores HC1), para comparar").font = SEC_FONT
    r += 1
    hdr(ws, r, ["Nº", "Modelo", "Anuncios", "Por debajo de lo previsto (%)", "Calidad intrínseca mediana", "Precio mediano (€)", "Segmento",
                "Puesto nuevo"])
    r += 1
    for i, d in enumerate(res["infravalorados_ant"][:20], 1):
        for j, v in enumerate([i, d["modelo"], d["n"], d["pct"], d["calidad_intr"], d["precio_mediano"], d["segmento"], d.get("pos_nueva")], 1):
            c = ws.cell(r, j, v)
            c.font = _font(BLUE)
            if j == 4:
                c.number_format = "0.0%"
        r += 1
    for col, w in zip("ABCDEFGHIJKL", [5, 30, 40, 7, 10, 11, 12, 12, 14, 12, 12, 40]):
        ws.column_dimensions[col].width = w


def write_workbook(path: Path, res: dict) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    names = Names(wb)
    build_supuestos(wb, res, names)
    n_last = build_anuncios(wb, res["ads"], names)
    build_precios(wb, res, n_last)
    build_depreciacion(wb, res)
    build_oferta(wb, res, n_last)
    build_primas(wb, res)
    build_frontera(wb, res, n_last)
    build_top(wb, res, n_last)
    build_sensibilidad(wb, res)
    order = ["Anuncios", "Precios por modelo", "Depreciación", "Oferta", "Primas", "Frontera", "Top por franja", "Sensibilidad", "Supuestos"]
    wb._sheets = [wb[n] for n in order]
    for ws in wb.worksheets:
        ws.freeze_panes = None
    wb.save(path)
