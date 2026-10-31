"""Normalización de marca, modelo, motor, combustible y segmento."""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

BRAND_ALIASES = {
    "vw": "Volkswagen", "volkswagen": "Volkswagen", "volkswage": "Volkswagen",
    "seat": "Seat", "cupra": "Cupra", "skoda": "Skoda", "škoda": "Skoda",
    "toyota": "Toyota", "honda": "Honda", "mazda": "Mazda", "kia": "Kia",
    "hyundai": "Hyundai", "opel": "Opel", "vauxhall": "Opel", "renault": "Renault",
    "dacia": "Dacia", "peugeot": "Peugeot", "citroen": "Citroën", "citroën": "Citroën",
    "ds": "DS", "ford": "Ford", "fiat": "Fiat", "nissan": "Nissan", "suzuki": "Suzuki",
    "mitsubishi": "Mitsubishi", "chevrolet": "Chevrolet", "lancia": "Lancia",
    "alfa romeo": "Alfa Romeo", "alfa": "Alfa Romeo", "mini": "MINI", "smart": "smart",
    "audi": "Audi", "bmw": "BMW", "mercedes": "Mercedes-Benz", "mercedes-benz": "Mercedes-Benz",
    "lexus": "Lexus", "subaru": "Subaru", "daihatsu": "Daihatsu",
}

# modelo canónico -> (segmento, alias en minúsculas)
MODELS = {
    "Toyota": {"Yaris": ("utilitario", ["yaris"]), "Auris": ("compacto", ["auris"]),
               "Corolla": ("compacto", ["corolla"]), "Aygo": ("utilitario", ["aygo"]),
               "iQ": ("utilitario", ["iq"]), "Prius": ("compacto", ["prius"]), "Verso": ("monovolumen", ["verso"])},
    "Honda": {"Jazz": ("utilitario", ["jazz"]), "Civic": ("compacto", ["civic"]), "Insight": ("compacto", ["insight"])},
    "Mazda": {"2": ("utilitario", ["mazda2", "mazda 2", "2"]), "3": ("compacto", ["mazda3", "mazda 3", "3"])},
    "Kia": {"Picanto": ("utilitario", ["picanto"]), "Rio": ("utilitario", ["rio"]),
            "Ceed": ("compacto", ["ceed", "cee'd", "cee d", "pro ceed", "proceed"]), "Venga": ("monovolumen", ["venga"])},
    "Hyundai": {"i10": ("utilitario", ["i10"]), "i20": ("utilitario", ["i20"]), "i30": ("compacto", ["i30"]),
                "Getz": ("utilitario", ["getz"]), "ix20": ("monovolumen", ["ix20"])},
    "Skoda": {"Fabia": ("utilitario", ["fabia"]), "Octavia": ("compacto", ["octavia"]),
              "Rapid": ("compacto", ["rapid"]), "Citigo": ("utilitario", ["citigo"])},
    "Seat": {"Ibiza": ("utilitario", ["ibiza"]), "León": ("compacto", ["leon", "león"]),
             "Mii": ("utilitario", ["mii"]), "Arosa": ("utilitario", ["arosa"]), "Altea": ("monovolumen", ["altea"])},
    "Volkswagen": {"Polo": ("utilitario", ["polo"]), "Golf": ("compacto", ["golf"]),
                   "up!": ("utilitario", ["up!", "up"]), "Fox": ("utilitario", ["fox"])},
    "Opel": {"Corsa": ("utilitario", ["corsa"]), "Astra": ("compacto", ["astra"]),
             "Adam": ("utilitario", ["adam"]), "Agila": ("utilitario", ["agila"]), "Meriva": ("monovolumen", ["meriva"])},
    "Renault": {"Clio": ("utilitario", ["clio"]), "Mégane": ("compacto", ["megane", "mégane"]),
                "Twingo": ("utilitario", ["twingo"]), "Modus": ("monovolumen", ["modus"])},
    "Dacia": {"Sandero": ("utilitario", ["sandero"]), "Logan": ("compacto", ["logan"])},
    "Peugeot": {"107": ("utilitario", ["107"]), "108": ("utilitario", ["108"]), "207": ("utilitario", ["207"]),
                "208": ("utilitario", ["208"]), "308": ("compacto", ["308"])},
    "Citroën": {"C1": ("utilitario", ["c1"]), "C3": ("utilitario", ["c3"]), "C4": ("compacto", ["c4"]),
                "C-Elysée": ("compacto", ["c-elysee", "c elysee", "c-elysée"])},
    "Ford": {"Ka": ("utilitario", ["ka", "ka+"]), "Fiesta": ("utilitario", ["fiesta"]), "Focus": ("compacto", ["focus"])},
    "Fiat": {"Panda": ("utilitario", ["panda"]), "Punto": ("utilitario", ["punto", "grande punto", "punto evo"]),
             "500": ("utilitario", ["500"]), "Bravo": ("compacto", ["bravo"]), "Tipo": ("compacto", ["tipo"])},
    "Nissan": {"Micra": ("utilitario", ["micra"]), "Note": ("monovolumen", ["note"]), "Pulsar": ("compacto", ["pulsar"])},
    "Suzuki": {"Swift": ("utilitario", ["swift"]), "Alto": ("utilitario", ["alto"]), "Splash": ("utilitario", ["splash"]),
               "Baleno": ("utilitario", ["baleno"]), "Celerio": ("utilitario", ["celerio"])},
    "Mitsubishi": {"Colt": ("utilitario", ["colt"]), "Space Star": ("utilitario", ["space star"])},
    "Chevrolet": {"Aveo": ("utilitario", ["aveo"]), "Spark": ("utilitario", ["spark"]), "Cruze": ("compacto", ["cruze"])},
}

# Patrones de tecnología de motor -> etiqueta canónica
ENGINE_TECH = [
    (r"pure\s*tech", "PureTech"),
    (r"\bthp\b", "THP"),
    (r"\bvti\b", "VTi"),
    (r"eco\s*boost", "EcoBoost"),
    (r"\btce\b", "TCe"),
    (r"\bsce\b", "SCe"),
    (r"\btsi\b", "TSI"),
    (r"\btfsi\b", "TFSI"),
    (r"\bmpi\b", "MPI"),
    (r"\bfsi\b", "FSI"),
    (r"skyactiv|sky\s*activ", "Skyactiv-G"),
    (r"i-?vtec", "i-VTEC"),
    (r"vvt-?i|dual\s*vvt", "VVT-i"),
    (r"\bt-?jet\b", "T-Jet"),
    (r"multiair", "MultiAir"),
    (r"fire\b", "FIRE"),
    (r"\bdig-?t\b", "DIG-T"),
    (r"\bt-?gdi\b", "T-GDi"),
    (r"\bcrdi\b", "CRDi"),
    (r"\btdi\b", "TDI"),
    (r"\bhdi\b|bluehdi|e-?hdi", "HDi"),
    (r"\bdci\b", "dCi"),
    (r"\bcdti\b", "CDTi"),
    (r"\btdci\b", "TDCi"),
    (r"\bd-?4d\b", "D-4D"),
    (r"\bjtd|multijet", "Multijet"),
    (r"\bi-?dtec|i-?ctdi", "i-DTEC"),
    (r"h[ií]brid|hybrid|\bhsd\b|\bhev\b", "Hybrid"),
    (r"\bturbo\b", "Turbo"),
]

FUEL_PATTERNS = [
    (r"h[ií]brid|hybrid|\bhev\b|\bhsd\b", "hibrido"),
    (r"\bglp\b|\blpg\b|bi-?fuel|autogas", "glp"),
    (r"di[eé]sel|gasoil|\btdi\b|\bhdi\b|\bdci\b|\bcrdi\b|\bcdti\b|\btdci\b|d-?4d|multijet|i-?dtec|\bjtd", "diesel"),
    (r"el[eé]ctrico|\bev\b|\bbev\b", "electrico"),
    (r"gasolina|\btsi\b|\bmpi\b|vvt|vtec|tce|puretech|ecoboost|skyactiv|\bsce\b|\bfsi\b", "gasolina"),
]


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm_text(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", strip_accents((s or "").lower())).strip()


def norm_brand(raw: Optional[str], titulo: str = "") -> Optional[str]:
    for cand in (raw, titulo):
        t = norm_text(cand)
        if not t:
            continue
        # alias más largos primero ("alfa romeo" antes que "alfa")
        for alias in sorted(BRAND_ALIASES, key=len, reverse=True):
            if re.search(rf"(^|\W){re.escape(strip_accents(alias))}(\W|$)", t):
                return BRAND_ALIASES[alias]
    return None


def norm_model(marca: Optional[str], raw: Optional[str], titulo: str = "") -> tuple[Optional[str], Optional[str]]:
    """Devuelve (modelo canónico, segmento)."""
    if not marca or marca not in MODELS:
        return (raw.strip().title() if raw else None), None
    for cand in (raw, titulo):
        t = norm_text(cand)
        if not t:
            continue
        options = [(alias, name, seg) for name, (seg, aliases) in MODELS[marca].items() for alias in aliases]
        for alias, name, seg in sorted(options, key=lambda x: len(x[0]), reverse=True):
            a = strip_accents(alias)
            # alias numéricos cortos ("2", "3") solo valen si el campo es el modelo, no el título
            if len(a) <= 1 and cand is titulo:
                continue
            if re.search(rf"(^|[^\w]){re.escape(a)}([^\w]|$)", t):
                return name, seg
    return (raw.strip().title() if raw else None), None


def parse_displacement(text: str) -> Optional[float]:
    """Litros con un decimal (1.33 se mantiene) a partir de '1.4', '1,4', '1398 cc', '1400cc'."""
    t = norm_text(text)
    m = re.search(r"(\d{3,4})\s*(cc|cm3|c\.c\.)", t)
    if m:
        cc = int(m.group(1))
        if 600 <= cc <= 3000:
            return round(cc / 1000, 1)
    m = re.search(r"(?<![\d.,])([0-3])[.,](\d{1,2})(?![\d])", t)
    if m:
        val = float(f"{m.group(1)}.{m.group(2)}")
        if 0.6 <= val <= 3.0:
            return 1.33 if abs(val - 1.33) < 0.005 else round(val, 1)
    return None


def norm_engine(*texts: Optional[str]) -> Optional[str]:
    """'1.4 16v TSI 122cv' -> '1.4 TSI'. '1,2 PureTech' -> '1.2 PureTech'."""
    joined = " ".join(t for t in texts if t)
    t = norm_text(joined)
    disp = parse_displacement(joined)
    tech = None
    for pat, label in ENGINE_TECH:
        if re.search(pat, t):
            tech = label
            break
    if disp is None and tech is None:
        return None
    d = (f"{disp:.2f}".rstrip("0").rstrip(".") if disp == 1.33 else f"{disp:.1f}") if disp else "?"
    return f"{d} {tech}" if tech else d


def norm_fuel(raw: Optional[str], *texts: Optional[str]) -> Optional[str]:
    for cand in (raw, " ".join(t for t in texts if t)):
        t = norm_text(cand)
        if not t:
            continue
        for pat, label in FUEL_PATTERNS:
            if re.search(pat, t):
                return label
    return None


def norm_gearbox(raw: Optional[str], *texts: Optional[str]) -> Optional[str]:
    t = norm_text(" ".join(x for x in (raw, *texts) if x))
    if re.search(r"autom[aá]tic|\bdsg\b|\bcvt\b|e-?cvt|tiptronic|\bedc\b|powershift|\bamt\b|s-?tronic|i-?shift|easytronic|\beat\b", t):
        return "automatico"
    if re.search(r"manual", t):
        return "manual"
    return None


def norm_seller(raw: Optional[str]) -> Optional[str]:
    t = norm_text(raw)
    if not t:
        return None
    if any(k in t for k in ("profesional", "concesionario", "dealer", "pro", "empresa", "compraventa")):
        return "profesional"
    if any(k in t for k in ("particular", "private", "privado")):
        return "particular"
    return None


def potencia_cv(text: str) -> Optional[int]:
    t = norm_text(text)
    m = re.search(r"(\d{2,3})\s*(cv|hp|ps)\b", t)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{2,3})\s*kw\b", t)
    if m:
        return round(int(m.group(1)) * 1.35962)
    return None
