"""Interfaz común de las plataformas.

Cada plataforma implementa:
  search(since)            -> iterador de Listing "parciales" (lo que da la página/JSON de resultados)
  detail(listing)          -> Listing completo (descripción, fotos, vendedor...) si el listado no lo trae
  needs_detail(listing)    -> True si hay que pedir la ficha

Política (ver src/http.py): robots.txt, una petición a la vez por dominio, pausa 2-5 s,
caché en /raw, y si hay bloqueo (captcha/403/429) se para la plataforma y se registra.
"""
from __future__ import annotations

from typing import Iterator, Optional

from ..http import PoliteClient
from ..models import Listing


class NotReadyError(RuntimeError):
    """La plataforma aún no tiene método validado (pendiente de reconocimiento)."""


class Source:
    name = "base"
    # Método elegido tras el reconocimiento: 'api-json' | 'json-embebido' | 'html' | 'playwright' | None
    metodo: Optional[str] = None
    estado = "PENDIENTE de reconocimiento (sin acceso de red en el entorno de desarrollo)"

    def __init__(self, client: PoliteClient, cfg: dict, src_cfg: dict):
        self.client = client
        self.cfg = cfg
        self.src_cfg = src_cfg

    def search(self, since: Optional[str] = None) -> Iterator[Listing]:
        raise NotReadyError(f"{self.name}: {self.estado}")

    def needs_detail(self, l: Listing) -> bool:
        return not l.descripcion

    def detail(self, l: Listing) -> Listing:
        return l
