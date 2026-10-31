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

## Alertas y ejecución periódica

### Telegram (bot propio)
1. En Telegram, abre **@BotFather** → `/newbot` y copia el token.
2. Escribe un mensaje a tu bot y abre `https://api.telegram.org/bot<TOKEN>/getUpdates` para ver tu `chat.id`.
3. `cp .env.example .env` y rellena `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`. `.env` está en `.gitignore`, así que no se sube.

Se avisa de cada anuncio **nuevo** con puntuación ≥ `alertas.umbral_puntuacion` (55 por defecto), dentro de presupuesto
o en el margen de negociación, y que no haya caído en los filtros de fraude. El mensaje lleva modelo, año, km, coste total,
puntuación, avisos y enlace. Sin `.env`, las alertas solo se escriben en `logs/alertas.log`.

### Opción A: dejarlo corriendo
```bash
python run.py --watch        # ejecuta, avisa y repite cada alertas.intervalo_horas (4 h)
```

### Opción B: programarlo (recomendado; sobrevive a reinicios)
**Linux / macOS (cron)**: `crontab -e` y añade (ajusta rutas):
```
17 */4 * * * cd /ruta/a/buscador-coches && /usr/bin/python3 run.py >> logs/cron.log 2>&1
```
**Windows (Programador de tareas)**: en PowerShell (ajusta rutas):
```powershell
schtasks /Create /TN "BuscadorCoches" /SC HOURLY /MO 4 /ST 08:17 `
  /TR "cmd /c cd /d C:\ruta\buscador-coches && C:\Python313\python.exe run.py >> logs\cron.log 2>&1"
```
o en la interfaz: Programador de tareas → Crear tarea básica → Diariamente → Repetir cada 4 horas →
Iniciar un programa: `python.exe`, argumentos `run.py`, iniciar en `C:\ruta\buscador-coches`.

Cada ejecución solo abre la ficha de los anuncios nuevos. La caché de listados dura `http.cache_ttl_horas` (3 h), así que
cada ejecución de 4 h ve los anuncios recientes.

### Tiempo hasta la venta
Un anuncio (de los candidatos y de todo el mercado visto) se marca como desaparecido tras
`seguimiento.ejecuciones_para_desaparecido` ejecuciones correctas seguidas sin verlo. `informe.md` resume la mediana de
días por modelo y tramo de precio. En fuentes con cobertura parcial (tope de páginas de Coches.net, ~80 por página en
Wallapop), desaparecer puede significar haber salido de las páginas accesibles: es una estimación.

## Distintivo ambiental (DGT) y ZBE
- La etiqueta de cada anuncio se obtiene, por orden: 1) **fichero oficial de la DGT** por matrícula
  ("Microdatos de distintivo ambiental de vehículos (diarios)", ~38,7 M matrículas; se descarga como mucho una vez al día
  y se indexa en `data/dgt/distintivos.sqlite`, unos 840 MB, fuera del repositorio); 2) la etiqueta que publica el anuncio;
  3) la **regla** de la DGT por combustible y fecha de primera matriculación (`zbe.yaml`). En un año frontera sin mes conocido,
  la etiqueta es "dudosa" y se asigna la peor posible.
- Filtro: `filtros.etiqueta_minima` (B). Las dudosas no se descartan: entran con el aviso "confirmar etiqueta con la DGT".
- Puntuación: criterio "Etiqueta y ZBE" (`scoring.pesos.etiqueta`, 6 %), con B 40, C 70 y ECO/CERO 100, −15 si es dudosa y −5 si sale
  solo de la regla.
- `python tools/dgt_check.py` vuelve a validar la equivalencia de los códigos del fichero DGT con las etiquetas de OcasionPlus.
- Estado de la ZBE de València: ordenanza pendiente de aprobación definitiva; calendario previsto y fuentes en `zbe.yaml`.
