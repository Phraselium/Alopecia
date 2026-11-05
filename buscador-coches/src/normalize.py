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
               "iQ": ("utilitario", ["iq"]), "Prius": ("compacto", ["prius"]), "Verso": ("monovolumen", ["verso"]), "Avensis": ("berlina_d", ["avensis"])},
    "Honda": {"Jazz": ("utilitario", ["jazz"]), "CR-V": ("suv", ["cr-v", "crv"]), "Accord": ("berlina_d", ["accord"]), "Civic": ("compacto", ["civic"]), "Insight": ("compacto", ["insight"])},
    "Mazda": {"2": ("utilitario", ["mazda2", "mazda 2", "2"]), "3": ("compacto", ["mazda3", "mazda 3", "3"]),
              "5": ("monovolumen", ["mazda5", "mazda 5", "5"]), "6": ("berlina_d", ["mazda6", "mazda 6", "6"])},
    "Kia": {"Picanto": ("utilitario", ["picanto"]), "Rio": ("utilitario", ["rio"]),
            "Ceed": ("compacto", ["ceed", "cee'd", "cee d", "pro ceed", "proceed"]), "Venga": ("monovolumen_pequeno", ["venga"])},
    "Hyundai": {"i10": ("utilitario", ["i10"]), "i20": ("utilitario", ["i20"]), "i30": ("compacto", ["i30"]),
                "Getz": ("utilitario", ["getz"]), "Matrix": ("monovolumen_pequeno", ["matrix"]), "Tucson": ("suv", ["tucson"]), "ix20": ("monovolumen_pequeno", ["ix20"])},
    "Skoda": {"Fabia": ("utilitario", ["fabia"]), "Octavia": ("compacto", ["octavia"]),
              "Rapid": ("berlina", ["rapid"]), "Citigo": ("utilitario", ["citigo"]), "Superb": ("berlina_d", ["superb"]), "Yeti": ("suv", ["yeti"])},
    "Seat": {"Ibiza": ("utilitario", ["ibiza"]), "León": ("compacto", ["leon", "león"]),
             "Mii": ("utilitario", ["mii"]), "Arosa": ("utilitario", ["arosa"]), "Altea": ("monovolumen_pequeno", ["altea"]), "Córdoba": ("berlina", ["cordoba", "córdoba"]), "Exeo": ("berlina_d", ["exeo"]), "Toledo": ("berlina", ["toledo"])},
    "Volkswagen": {"Polo": ("utilitario", ["polo"]), "Golf": ("compacto", ["golf"]),
                   "up!": ("utilitario", ["up!", "up"]), "Fox": ("utilitario", ["fox"]),
                   "Beetle": ("compacto", ["beetle", "escarabajo"]), "Touran": ("monovolumen", ["touran"]), "Jetta": ("berlina", ["jetta"]), "Touareg": ("suv", ["touareg"]), "Tiguan": ("suv", ["tiguan"])},
    "Opel": {"Corsa": ("utilitario", ["corsa"]), "Astra": ("compacto", ["astra"]),
             "Adam": ("utilitario", ["adam"]), "Agila": ("utilitario", ["agila"]), "Meriva": ("monovolumen_pequeno", ["meriva"]), "Zafira": ("monovolumen", ["zafira"]),
             "Karl": ("utilitario", ["karl"]), "Insignia": ("berlina_d", ["insignia"]), "Antara": ("suv", ["antara"])},
    "Renault": {"Clio": ("utilitario", ["clio"]), "Mégane": ("compacto", ["megane", "mégane"]),
                "Twingo": ("utilitario", ["twingo"]), "Modus": ("monovolumen_pequeno", ["modus"]), "Fluence": ("berlina", ["fluence"]), "Laguna": ("berlina_d", ["laguna"]),
                "Scénic": ("monovolumen", ["scenic", "scénic", "grand scenic"])},
    "Dacia": {"Sandero": ("utilitario", ["sandero"]), "Logan": ("berlina", ["logan"])},
    "Peugeot": {"107": ("utilitario", ["107"]), "108": ("utilitario", ["108"]), "206": ("utilitario", ["206", "206+"]), "207": ("utilitario", ["207"]), "508": ("berlina_d", ["508"]),
                "5008": ("monovolumen", ["5008"]), "Partner": ("furgoneta", ["partner"]),
                "208": ("utilitario", ["208"]), "308": ("compacto", ["308"]), "301": ("berlina", ["301"]), "2008": ("suv", ["2008"]), "3008": ("suv", ["3008"])},
    "Citroën": {"C1": ("utilitario", ["c1"]), "C2": ("utilitario", ["c2"]), "C3": ("utilitario", ["c3"]), "C4": ("compacto", ["c4"]),
                "C-Elysée": ("berlina", ["c-elysee", "c elysee", "c-elysée"]),
                "C3 Picasso": ("monovolumen_pequeno", ["c3 picasso"]), "Xsara Picasso": ("monovolumen", ["xsara picasso"]),
                "C4 Picasso": ("monovolumen", ["c4 picasso", "grand c4 picasso"])},
    "Ford": {"Ka": ("utilitario", ["ka", "ka+"]), "Fiesta": ("utilitario", ["fiesta"]), "Focus": ("compacto", ["focus"]),
             "B-Max": ("monovolumen_pequeno", ["b-max", "b max", "bmax"]), "C-Max": ("monovolumen", ["c-max", "c max", "cmax"]),
             "Fusion": ("monovolumen_pequeno", ["fusion"]), "Mondeo": ("berlina_d", ["mondeo"]),
             "Connect": ("furgoneta", ["connect", "transit connect", "tourneo connect"]), "Kuga": ("suv", ["kuga"])},
    "Fiat": {"Panda": ("utilitario", ["panda"]), "Punto": ("utilitario", ["punto", "grande punto", "punto evo"]),
             "500": ("utilitario", ["500"]), "Bravo": ("compacto", ["bravo"]), "Linea": ("berlina", ["linea"]), "Tipo": ("compacto", ["tipo"])},
    "Nissan": {"Micra": ("utilitario", ["micra"]), "Pixo": ("utilitario", ["pixo"]), "Qashqai": ("suv", ["qashqai"]),
               "Juke": ("suv", ["juke"]), "Leaf": ("utilitario", ["leaf"]), "Note": ("monovolumen_pequeno", ["note"]), "Pulsar": ("compacto", ["pulsar"])},
    "Suzuki": {"Swift": ("utilitario", ["swift"]), "Alto": ("utilitario", ["alto"]), "Splash": ("utilitario", ["splash"]),
               "Baleno": ("utilitario", ["baleno"]), "Celerio": ("utilitario", ["celerio"])},
    "Mitsubishi": {"Colt": ("utilitario", ["colt"]), "Space Star": ("utilitario", ["space star"])},
    "Audi": {"A1": ("utilitario", ["a1"]), "A3": ("compacto", ["a3"]), "A4": ("berlina_d", ["a4"])},
    "Alfa Romeo": {"147": ("compacto", ["147"]), "159": ("berlina_d", ["159"]), "MiTo": ("utilitario", ["mito"]),
                   "Giulietta": ("compacto", ["giulietta"])},
    "MINI": {"MINI": ("utilitario", ["mini", "cooper", "one"])},
    "Mercedes-Benz": {"Clase A": ("compacto", ["clase a", "a 160", "a 180", "a 200", "a160", "a180", "a200"]),
                      "Clase B": ("monovolumen_pequeno", ["clase b", "b 180", "b 200", "b180", "b200"])},
    "smart": {"forfour": ("utilitario", ["forfour"]), "fortwo": ("utilitario", ["fortwo"])},
    "Chevrolet": {"Kalos": ("utilitario", ["kalos"]), "Matiz": ("utilitario", ["matiz"]), "Nubira": ("compacto", ["nubira"]),
                  "Epica": ("berlina_d", ["epica"]), "Captiva": ("suv", ["captiva"]),
                  "Aveo": ("utilitario", ["aveo"]), "Spark": ("utilitario", ["spark"]), "Cruze": ("compacto", ["cruze"])},
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
    """Devuelve (modelo canónico, segmento). Busca en el modelo del anuncio y en el título y se queda con el
    alias MÁS LARGO que coincida (así 'C4 Picasso' gana a 'C4' aunque el campo modelo diga solo 'C4')."""
    if not marca or marca not in MODELS:
        return (raw.strip().title() if raw else None), None
    options = [(alias, name, seg) for name, (seg, aliases) in MODELS[marca].items() for alias in aliases]
    best = None
    for cand in (raw, titulo):
        t = norm_text(cand)
        if not t:
            continue
        for alias, name, seg in options:
            a = strip_accents(alias)
            # alias numéricos cortos ("2", "3") solo valen si el campo es el modelo, no el título
            if len(a) <= 1 and cand is titulo:
                continue
            if re.search(rf"(^|[^\w]){re.escape(a)}([^\w]|$)", t) and (best is None or len(a) > len(best[0])):
                best = (a, name, seg)
    if best:
        return best[1], best[2]
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
    joined = " ".join(str(t) for t in texts if t)
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


_DIESEL_TOKEN = r"\b(tdi|hdi|bluehdi|dci|crdi|cdti|tdci|jtd\w*|multijet|d-?4d|i-?dtec|i-?ctdi|cdi|ddis|dtec)\b"


def norm_fuel(raw: Optional[str], *texts: Optional[str]) -> Optional[str]:
    # Una sigla de motor diésel inequívoca en el título/versión manda sobre la etiqueta de la plataforma
    # (Wallapop marca a veces "gasolina" un Alfa 159 JTD)
    if texts and texts[0] and re.search(_DIESEL_TOKEN, norm_text(str(texts[0]))):
        return "diesel"
    for cand in (raw, " ".join(str(t) for t in texts if t)):
        t = norm_text(cand)
        if not t:
            continue
        for pat, label in FUEL_PATTERNS:
            if re.search(pat, t):
                return label
    return None


def norm_gearbox(raw: Optional[str], *texts: Optional[str]) -> Optional[str]:
    t = norm_text(" ".join(str(x) for x in (raw, *texts) if x))
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


BODY_KEYWORDS = [
    (r"\b(cc|cabrio\w*|coup[eé]|roadster|descapotable|spider)\b", "cabrio"),
    (r"\b(st|sw|sportwagon|sports? ?wagon|sports? ?tourer|variant|combi|break|touring|estate|kombi|mcv|grand ?tour"
     r"|sportbreak|sport ?brake|tourer|cw|sportswagon|familiar|caravan|avant|wagon)\b", "familiar"),
    (r"\b(sedan|sed[aá]n|4p|4 puertas)\b", "berlina"),
    (r"\b(4x4|crossover|suv|cross|x-?cross|stepway|aircross|countryman)\b", "suv"),
]


def body_from_text(text: str) -> Optional[str]:
    t = norm_text(text)
    for pat, body in BODY_KEYWORDS:
        if re.search(pat, t):
            return body
    return None
