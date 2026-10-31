"""Coches.net (Adevinta)

Reconocimiento (Fase 0) PENDIENTE: el entorno de desarrollo no tiene acceso de red a www.coches.net.
Hipótesis a comprobar antes de programar el parser (no verificadas):
- La web consume una API JSON interna de búsqueda; protección antibots fuerte probable.
- Si devuelve captcha/403, se registra y se salta (no se intenta esquivar).
"""
from __future__ import annotations

from .base import Source


class CochesNet(Source):
    name = "cochesnet"
    dominio = "www.coches.net"
