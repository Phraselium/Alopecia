"""AutoScout24 España

Reconocimiento (Fase 0) PENDIENTE: el entorno de desarrollo no tiene acceso de red a www.autoscout24.es.
Hipótesis a comprobar antes de programar el parser (no verificadas):
- Páginas de resultados Next.js con JSON embebido (__NEXT_DATA__) -> requests + json, sin Playwright.
- Filtros por URL: precio, año, km, combustible, código postal + radio.
"""
from __future__ import annotations

from .base import Source


class AutoScout24(Source):
    name = "autoscout24"
    dominio = "www.autoscout24.es"
