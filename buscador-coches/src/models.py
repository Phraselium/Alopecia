"""Modelo de datos común a todas las plataformas."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Listing:
    plataforma: str
    id_externo: str
    url: str
    titulo: str
    precio: Optional[float] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    version: Optional[str] = None
    cilindrada_cc: Optional[int] = None
    potencia_cv: Optional[int] = None
    combustible: Optional[str] = None      # gasolina | diesel | hibrido | glp | electrico
    anio: Optional[int] = None
    km: Optional[int] = None
    cambio: Optional[str] = None           # manual | automatico
    carroceria: Optional[str] = None
    vendedor: Optional[str] = None         # particular | profesional
    ubicacion: Optional[str] = None
    distancia_km: Optional[float] = None
    fecha_publicacion: Optional[str] = None  # ISO 8601
    num_fotos: Optional[int] = None
    descripcion: str = ""
    # Señales extraídas del texto (None = no lo menciona)
    itv_vigor: Optional[bool] = None
    libro_mantenimiento: Optional[bool] = None
    correa_cambiada: Optional[bool] = None
    num_propietarios: Optional[int] = None
    garantia: Optional[bool] = None
    km_justificados: Optional[bool] = None
    # Compra a profesional / seguridad de compra
    garantia_meses: Optional[int] = None          # garantía incluida en el precio
    garantia_ampliable: Optional[bool] = None
    garantia_ampliacion_eur: Optional[float] = None
    garantia_ampliacion_meses: Optional[int] = None
    revision_puntos: Optional[int] = None
    km_certificados: Optional[bool] = None
    devolucion_dias: Optional[int] = None
    precio_contado: Optional[float] = None
    precio_financiado: Optional[float] = None
    solo_financiando: Optional[bool] = None       # el precio anunciado solo vale financiando
    gastos_gestion_eur: Optional[float] = None    # gastos de gestión/preparación/transferencia del vendedor
    gastos_incluyen_transferencia: Optional[bool] = None
    # Distintivo ambiental
    matricula: Optional[str] = None
    fecha_matriculacion: Optional[str] = None     # 'YYYY-MM-DD', 'YYYY-MM', 'MM/YYYY' o 'YYYY'
    etiqueta_anuncio: Optional[str] = None        # la que publica la plataforma
    etiqueta_fuente: Optional[str] = None         # DGT | anuncio | regla
    etiqueta_dudosa: Optional[bool] = None
    etiqueta_codigo_dgt: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    # Campos normalizados / calculados en Python
    motor_key: Optional[str] = None        # p. ej. "1.2 PureTech"
    modelo_key: Optional[str] = None       # p. ej. "Peugeot 208"
    etiqueta_dgt: Optional[str] = None
    raw_ref: Optional[str] = None          # fichero de /raw del que sale
    fuente_dato: Optional[str] = None      # endpoint/método usado
    duplicados: list = field(default_factory=list)
    revisar: list = field(default_factory=list)   # expresiones ambiguas o falta de ITV: revisar, no descartar
    anio_alternativo: Optional[int] = None
    caja_robotizada: Optional[str] = None
    etiqueta_dudosa_anio: Optional[bool] = None    # dudosa porque el año de la URL/título cambia la etiqueta posible          # texto detectado (p. ej. "easytronic")        # año distinto en la URL o el título ("año a confirmar")
    descartes: list = field(default_factory=list)

    @property
    def uid(self) -> str:
        return f"{self.plataforma}:{self.id_externo}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["uid"] = self.uid
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Listing":
        d = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**d)
