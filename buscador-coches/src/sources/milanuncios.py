"""Milanuncios (Adevinta)

Reconocimiento (Fase 0) PENDIENTE: el entorno de desarrollo no tiene acceso de red a www.milanuncios.com.
Hipótesis a comprobar antes de programar el parser (no verificadas):
- Protección antibots fuerte probable (captcha). Si bloquea, se registra y se salta.
- Si es accesible: JSON embebido en la página de resultados.
"""
from __future__ import annotations

from .base import Source


class Milanuncios(Source):
    name = "milanuncios"
    dominio = "www.milanuncios.com"
