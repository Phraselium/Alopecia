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
    multitronic: Optional[str] = None             # "sí" detectada / "posible" (Audi automático sin tiptronic/quattro)
    prioritario: Optional[bool] = None            # modelo/motor/años de la lista de preferencia de estilo
    etiqueta_dudosa_anio: Optional[bool] = None    # dudosa porque el año de la URL/título cambia la etiqueta posible          # texto detectado (p. ej. "easytronic")        # año distinto en la URL o el título ("año a confirmar")
    etiqueta_opciones: Optional[str] = None       # "B/C": etiquetas posibles (la final es la peor)
    etiqueta_incoherente: Optional[str] = None    # etiqueta del anuncio que contradice la regla (se usa la regla)
    # Estética, color y estado (src/atributos.py)
    color_raw: Optional[str] = None               # color tal como lo publica la plataforma o el texto
    color: Optional[str] = None                   # color normalizado (ver estetica.yaml -> colores)
    color_fuente: Optional[str] = None
    equipamiento: Optional[str] = None            # texto del equipamiento estructurado de la plataforma (si lo hay)
    at_acabado: Optional[str] = None              # acabado alto/deportivo detectado (Sport, FR, S-line...)
    at_llantas: Optional[str] = None              # "16+" | "sí" | "chapa"
    at_faros: Optional[bool] = None               # xenón / LED
    at_tintados: Optional[bool] = None
    estetica_modelo: Optional[int] = None         # 1-5 (estetica.yaml)
    estetica_ref: Optional[str] = None            # entrada de estetica.yaml aplicada
    esp: Optional[str] = None                     # "sí" | "no" | None
    esp_fuente: Optional[str] = None
    ncap_estrellas: Optional[float] = None
    ncap_ref: Optional[str] = None
    correa_detalle: Optional[bool] = None         # la correa cambiada se acompaña de fecha o km
    facturas: Optional[bool] = None
    neumaticos_nuevos: Optional[bool] = None
    itv_hasta: Optional[str] = None
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
