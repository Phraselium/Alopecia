# Buscador de coches de segunda mano — Valencia (≤ 5.000 € en total)

## Estado
| Parte | Estado |
|---|---|
| Esqueleto, normalización, limpieza, deduplicación, fraude, coste total, scoring, Excel, informe, run.py incremental | Hecho, con tests (`pytest`) |
| Fórmulas del Excel | Verificadas: LibreOffice recalcula y coincide celda a celda con `src/scoring.py` |
| Reconocimiento de plataformas (API/JSON/robots.txt) | **PENDIENTE**: el entorno de desarrollo no tiene salida de red |
| Parsers de Wallapop, AutoScout24, Autocasion, Coches.net, Milanuncios | **PENDIENTE** (una a una, validando 20-30 anuncios reales) |
| `fiscal.yaml` | ITP CV (6 % / cuotas fijas), tasas DGT, ZBE: *probable* (verificar en la fuente) |
| `reliability.yaml` | 6 modelos con dato TÜV, 4 marcas OCU; el resto **PENDIENTE** |

## Uso
```bash
pip install -r requirements.txt
python run.py                    # solo anuncios nuevos + regenera ranking.xlsx e informe.md
python run.py --solo wallapop --max-paginas 2
python run.py --sin-red          # regenera salidas con lo ya guardado
pytest -q
```

## Estructura
- `config.yaml` — ubicación, filtros, pesos y parámetros del scoring.
- `fiscal.yaml`, `reliability.yaml` — datos con fuente y estado (confirmado / probable / PENDIENTE).
- `src/http.py` — robots.txt, pausa aleatoria 2–5 s por dominio, caché en `raw/`, parada ante captcha/403/429.
- `src/sources/` — una clase por plataforma.
- `src/normalize.py`, `src/extract.py`, `src/dedupe.py`, `src/fraud.py`, `src/costs.py`, `src/scoring.py`.
- `src/excel.py` — `ranking.xlsx` (Anuncios, Top20, Supuestos) con fórmulas y colores azul/negro/verde.
- `src/report.py` — `informe.md` con los 10 mejores.
- `data/listings.sqlite` — histórico para el modo incremental. `logs/` — log y `descartados.csv`.
