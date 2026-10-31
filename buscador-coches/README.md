# Buscador de coches de segunda mano — Valencia (≤ 5.000 € en total)

Recoge anuncios de concesionarios profesionales con garantía y de portales, los limpia y deduplica, calcula
el coste total real (ITP o gastos del vendedor, tasas DGT) y los puntúa de 0 a 100. Entrega:

- `ranking.xlsx`, con las hojas **Anuncios**, **Top20** y **Supuestos**. El scoring va en fórmulas de Excel.
  Colores: azul = dato, negro = cálculo, verde = de otra hoja. Sin paneles inmovilizados.
- `informe.md`, con los 10 mejores: por qué destacan, riesgos del modelo y motor, qué revisar y qué preguntar.
- `muestras.md`, con una muestra de anuncios reales por plataforma para validar la extracción.
- `RECONOCIMIENTO.md`, con el método y el robots.txt de cada plataforma, y cuáles están bloqueadas o sin stock.

## Uso
```bash
pip install -r requirements.txt
python run.py                     # recoge SOLO anuncios nuevos de todas las fuentes activas y regenera las salidas
python run.py --solo ocasionplus  # una fuente
python run.py --sin-red           # regenera ranking.xlsx e informe.md con lo ya guardado
python tools/muestras.py 25       # regenera muestras.md
pytest -q                         # incluye recálculo del Excel con LibreOffice y comparación con Python
```

## Fuentes (31-10-2026)
| Fuente | Tipo | Estado |
|---|---|---|
| OcasionPlus | Profesional con garantía | Activa (JSON-LD + RSC) |
| Flexicar, Clicars, Autohero, Renew | Profesional con garantía | Vigilancia: hoy sin stock ≤ 4.600 € |
| AutoScout24 | Portal | Activa (`__NEXT_DATA__`, filtros en URL) |
| Coches.net | Portal | Activa (rutas marca/modelo/provincia; tope de 6 páginas por robots.txt) |
| Wallapop | Portal | Activa, solo rutas permitidas por robots.txt (sin la API interna) |
| Milanuncios, Autocasion, Spoticar | — | Bloqueadas (antibots); registradas |
| Das WeltAuto | — | Excluida por robots.txt |
| Toyota, Hyundai, Kia, Mazda, Honda | Programas de marca | Sin stock central accesible o sin stock en rango; ver `RECONOCIMIENTO.md` |

## Configuración
- `config.yaml`: ubicación y radio, presupuesto, filtros, pesos del scoring (6 criterios, incluido "Seguridad de compra" con un 15 %).
- `fiscal.yaml`: ITP de la Comunitat Valenciana (cuotas fijas confirmadas en la ATV), tasas DGT, etiqueta DGT, ZBE,
  garantía legal (TRLGDCU art. 120, RDL 7/2021) y seguro estimado. Cada dato lleva fuente y estado.
- `reliability.yaml`: fiabilidad por modelo (TÜV, ADAC Pannenstatistik 2025, OCU por marca) y problemas de motor con fuente.

Datos geográficos: GeoNames (CC BY 4.0), que se descargan solos en `data/geo/`.
