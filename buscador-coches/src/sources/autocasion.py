"""Autocasion

Reconocimiento (Fase 0) PENDIENTE: el entorno de desarrollo no tiene acceso de red a www.autocasion.com.
Hipótesis a comprobar antes de programar el parser (no verificadas):
- Listado en HTML de servidor -> requests + BeautifulSoup; posible JSON-LD por anuncio.
"""
from __future__ import annotations

from .base import Source


class Autocasion(Source):
    name = "autocasion"
    dominio = "www.autocasion.com"
