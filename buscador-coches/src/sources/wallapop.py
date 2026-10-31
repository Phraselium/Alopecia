"""Wallapop (coches)

Reconocimiento (Fase 0) PENDIENTE: el entorno de desarrollo no tiene acceso de red a es.wallapop.com / api.wallapop.com.
Hipótesis a comprobar antes de programar el parser (no verificadas):
- La web consume un endpoint JSON de búsqueda (api.wallapop.com/api/v3/...) con lat/lon, distancia,
  precio, año y km. Es interno, no una API pública documentada: usar solo si robots.txt no lo excluye.
- Ficha de cada anuncio: JSON del ítem o datos embebidos (__NEXT_DATA__).
"""
from __future__ import annotations

from .base import Source


class Wallapop(Source):
    name = "wallapop"
    dominio = "es.wallapop.com / api.wallapop.com"
