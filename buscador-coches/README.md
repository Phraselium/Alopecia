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

Se avisa de cada anuncio **nuevo** con puntuación ≥ `alertas.umbral_puntuacion` (alto, ver config.yaml) que pase todos los filtros (profesional, etiqueta confirmada ≥ B, averías, diésel, fraude), dentro de presupuesto
o en el margen de negociación, y que no haya caído en los filtros de fraude. El mensaje lleva modelo, año, km, coste total,
puntuación, avisos y enlace. Sin `.env`, las alertas solo se escriben en `logs/alertas.log`.

### Opción A: dejarlo corriendo
```bash
python run.py --watch        # ejecuta, avisa y repite cada alertas.intervalo_horas (24 h: una vez al día)
```

### Opción B: programarlo (recomendado; sobrevive a reinicios)
**Linux / macOS (cron)**: `crontab -e` y añade (ajusta rutas):
```
17 8 * * * cd /ruta/a/buscador-coches && /usr/bin/python3 run.py >> logs/cron.log 2>&1   # cada día a las 8:17
```
**Windows (Programador de tareas)**: en PowerShell (ajusta rutas):
```powershell
schtasks /Create /TN "BuscadorCoches" /SC DAILY /ST 08:17 `
  /TR "cmd /c cd /d C:\ruta\buscador-coches && C:\Python313\python.exe run.py >> logs\cron.log 2>&1"
```
o en la interfaz: Programador de tareas → Crear tarea básica → Diariamente (8:17) →
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

## Berlinas medianas sobrias (01-11-2026)

- Carrocerías `berlina` (segmento C) y `berlina_d` (segmento D) admitidas **sin penalización**. Familiar y monovolumen pequeño
  siguen penalizados.
- Criterio **Preferencia de estilo** (`scoring.pesos.estilo`, 10 % por defecto). Los modelos prioritarios
  (`scoring.estilo.prioritarios`: Accord 2.0, Avensis 1.8, Mazda 6 1.8/2.0, Octavia II 1.6, Jetta V 1.6, A4 B7 2.0/1.8T y Exeo
  gasolina) puntúan 100. El resto puntúa por segmento: berlina D 80 · berlina C 60 · compacto/familiar 50 · utilitario 15.
- **Excluidos siempre**: Peugeot 107, Toyota Aygo, Citroën C1 (`filtros.modelos_excluidos`) y la caja **Multitronic** de Audi
  (`filtros.excluir_multitronic`). Un Audi «automático» sin especificar entra con el aviso «confirmar que no es Multitronic».
- **Penalizaciones de motor** documentadas en `reliability.yaml`: EA888 1.8 TFSI/TSI 2007-2012 y 2.0 TFSI de Audi 2009-2012, por
  consumo de aceite (fuentes: Asghari v. VW de 2015, boletín Audi 11-24 y Auto Bild). El A4 B7 2.0 TFSI es EA113 y queda sin
  ajuste. El 1.4 TSI Twincharger 2005-2014 se penaliza por la cadena.
- **Coste de uso**: seguro estimado por segmento, con la berlina D en ~380 €/año. El consumo real de gasolina se toma por modelo
  o, si no hay dato, por segmento (`fiscal.yaml → consumo_estimado`, Spritmonitor). Las dos cosas son aproximadas.

## Estética, color, presupuesto suave y criterios nuevos (02-11-2026)

**Pesos** (`config.yaml → scoring.pesos`, suman 100 %; también en la hoja Supuestos):

| Criterio | Peso |
|---|---|
| Fiabilidad y durabilidad | 22 % |
| Precio frente al mercado | 15 % |
| Estado y mantenimiento | 12 % |
| Estética | 12 % |
| Seguridad (Euro NCAP y ESP) | 10 % |
| Seguridad de compra | 10 % |
| Coste de uso | 9 % |
| Km y edad | 5 % |
| Reventa y liquidez | 3 % |
| Color | 2 % |

**Etiqueta**
- La etiqueta final es la **peor de las posibles**: cualquier fecha del año, más el año que diga la URL o el título.
- Una etiqueta dudosa o deducida por regla solo descarta si alguna de sus opciones queda por debajo de `etiqueta_minima`. Se
  controla con `filtros.etiqueta_dudosa` y `filtros.etiqueta_regla` (`si_todas_cumplen` | `no`).
- Si el anuncio contradice la regla (por ejemplo, C en un gasolina de 2004), se usa la regla y se marca «anuncio incoherente».

**Particulares**
- Por defecto solo se admiten profesionales. La excepción son los modelos de `estetica.yaml` con 4 o 5 puntos
  (`filtros.particulares`).
- A los particulares se les añade el aviso «particular sin garantía: pedir informe DGT, historial ITV y revisión precompra».
- En seguridad de compra pierden 25 puntos (`penal_particular_sin_garantia`).
- Se muestra un **coste real estimado**, solo informativo: añade la reserva de correa y de neumáticos.

**Estética** (`estetica.yaml`, editable)
- El criterio pondera 2/3 los puntos del modelo (de 1 a 5) y 1/3 los atributos del anuncio.
- Suman: acabado alto o deportivo, llantas de aleación (más si son de 16" o más), faros xenón o LED y cristales tintados.
- Restan: tapacubos o llantas de chapa.

**Color**
- El texto se normaliza sin tildes («plateado» = plata, «antracita» = gris oscuro, «nacarado» = blanco).
- Puntuación: blanco, plata y gris medio, máxima; azul, gris oscuro y azul marino, media. Beige, dorado, champán, verdes claros y
  colores chillones restan.
- Negro y marrón oscuro se excluyen (`filtros.color`). Sin color o con un color no reconocido, la nota es neutra.

**Presupuesto**
- Hasta `total_max_eur` (5.000 €) no hay penalización.
- Hasta `techo_eur` (6.000 €) se restan `penal_por_100_eur` puntos (2) por cada 100 €, de forma proporcional, y el coche queda
  marcado «negociar». La columna «€ a negociar» indica lo que habría que rebajar.
- Por encima del techo, el coche queda excluido.

**Cajas robotizadas**: excluidas por defecto (`filtros.excluir_cajas_robotizadas`). Antes solo restaban 10 puntos de
fiabilidad.

**Criterios nuevos**
- **Seguridad**: estrellas Euro NCAP de la generación (`reliability.yaml → euroncap`; el protocolo cambió en 2009) y ESP/ESC.
  El ESP se toma del anuncio, del equipamiento de serie con fuente o de la obligación en turismos nuevos desde el 1-11-2014.
- **Estado y mantenimiento**: ITV, libro, propietarios, correa cambiada con fecha o km (un motor de cadena puntúa completo) y
  facturas.
- **Coste de uso**: consumo + seguro + mantenimiento (recambios por marca y tipo de distribución, en
  `reliability.yaml → mantenimiento`).
- **Reventa**: anuncios del modelo en el mercado recogido, días hasta que desaparece el anuncio (con al menos 3 ventas
  observadas) y etiqueta (C por encima de B).

**Datos estructurados**
- Color y equipamiento se leen de la ficha guardada en `raw/`: OcasionPlus `vehicle`, AutoScout24 `vehicle` y Coches.net `ad`.
- Para las fichas antiguas: `python tools/backfill_atributos.py`.

## Perfil «mercado»: visión global (01-11-2026)

Es un perfil independiente del personal: no usa `config.yaml` ni su base de datos.

| Parte | Fichero |
|---|---|
| Configuración | `config_mercado.yaml` |
| Supuestos con fuente | `mercado_supuestos.yaml`, `mercado_fiabilidad.yaml` |
| Base de datos | `data/mercado.sqlite` |
| Salidas | `mercado.xlsx`, `informe_mercado.md` |
| Código | `src/mercado/` |

```
python run_mercado.py                    # recoge todo y regenera las salidas
python run_mercado.py --solo cochesnet --sin-salidas   # una fuente (se pueden lanzar fuentes distintas en paralelo)
python run_mercado.py --sin-red          # regenera con lo guardado
python run_mercado.py --watch            # una vez al día: mide los días hasta que desaparece cada anuncio
python tools/verify_mercado.py           # recalcula mercado.xlsx con LibreOffice y lo compara con Python
```

**Alcance**
- Nuevos, km 0, seminuevos y usados, sin límite de precio ni de año, y todas las carrocerías, cambios y combustibles.
- Sin filtros personales (estética, colores, modelos excluidos, solo profesionales, exclusión de diésel).
- Solo se aplican el filtro estricto de averías (sobre el título) y el de fraude.

**Zonas**
- Provincia de Valencia como base.
- Madrid y Barcelona como referencia nacional: una muestra de 2-3 páginas por marca.

**Recogida a nivel de listado**
- No se abren fichas: con las pausas de 2-5 s, abrir cada una costaría unas 20 horas por ejecución.
- Coches.net:
  - Usados por marca y por modelo (página 6 como máximo, por robots.txt).
  - Km 0 de Valencia y una muestra nacional de 180 nuevos (su ruta de nuevos no filtra por provincia).
  - Los filtros de precio en la URL están prohibidos por robots.txt.
- AutoScout24: por marca, troceando por tramos de precio; trae el consumo WLTP y la generación.
- OcasionPlus: todo su stock de Valencia, con precio al contado.
- Flexicar: solo la primera página. El resto se carga desde `/api/`, que robots.txt prohíbe.
- Webs oficiales de marca: no viables (ver RECONOCIMIENTO.md).

**Coste total a 5 años** (12.000 km/año, configurable)
- Impuestos: ITP o tasa.
- Depreciación estimada con los propios datos.
- Seguro, energía (WLTP más el desfase real del ICCT, o consumo por defecto), mantenimiento, neumáticos e IVTM de València.
- Caballos fiscales según el RGV. La parte de uso anual (energía, seguro, mantenimiento, neumáticos e IVTM) se multiplica por los 5 años.

**Calidad**
- Mismos criterios y pesos que el perfil personal, sin estética ni color, renormalizados.
- La «calidad intrínseca» (sin precio ni coste de uso) es el eje de la frontera eficiente y del ratio calidad/coste.

**Análisis**
- Medianas por modelo, generación, año y km.
- Depreciación por segmento, combustible y marca: MCO con efectos fijos de modelo y errores HC1.
- Oferta y liquidez.
- Primas de etiqueta y de cambio automático (efectos fijos de modelo y año, errores HC1).
- Frontera eficiente y top 5 por franja y por segmento.
- Infravalorados: residuo de un modelo de valor.
