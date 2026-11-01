# Fase 0 — Reconocimiento de plataformas (2026-10-31)

Las copias de robots.txt están en `raw/recon/`, que no se sube a git. El parser propio está en `src/robots.py` y sigue RFC 9309.

| Plataforma | robots.txt (para navegadores genéricos) | Datos | Método elegido | Estado |
|---|---|---|---|---|
| **AutoScout24** | Prohíbe `/lst?…` y la API GraphQL. **Permite** `/lst/{marca}[/{modelo}]?filtros&page=N` y las fichas `/anuncios/…` | JSON `__NEXT_DATA__` → `listings` (20 por página): precio, km, matriculación, motor, cc, CV, cambio, tipo de vendedor, CP y ciudad | requests + JSON embebido, búsqueda por marca con filtros de CP y radio 50 km, precio, año y km aplicados en el servidor | Listo para implementar |
| **Coches.net** | Prohíbe **todos** los filtros por parámetro (precio, año, km, provincia, combustible, orden) y `pg≥7`. Permite páginas por ruta: `/segunda-mano/valencia/`, `/{marca}/segunda-mano/valencia/` y `?pg=2…6` | `window.__INITIAL_PROPS__` → `initialResults.items` (35 por página): precio, km, año, etiqueta ambiental, carrocería, profesional o no, ciudad | requests + JSON embebido, recorriendo marca (o marca/modelo) por ruta en la provincia 46, hasta la página 6, y filtrando el precio aquí | Implementable, con cobertura limitada por el tope de 6 páginas |
| **Wallapop** | Web: prohíbe `/search` y **cualquier URL con `?`**. Permite `/coches-segunda-mano/{lugar}` y `/item/{slug}`. `api.wallapop.com` **no tiene robots.txt** (redirige a la portada) | Página de categoría con `__NEXT_DATA__` → `seoLandingData.items` (unos 80, sin filtro de precio). La ficha `/item/…` da descripción, km, año, versión, CV, cambio, combustible, carrocería, lat/lon y CP | Opción A: categoría por ruta + fichas (poco volumen). Opción B: API de búsqueda interna (no hay robots.txt que la prohíba, pero el robots.txt de la web prohíbe las búsquedas) | **Decisión del usuario** |
| **Milanuncios** | Prohíbe casi todos los filtros, la paginación y `/api/` | — | — | **Bloqueado**: HTTP 405 con página antibots en la primera petición. Registrado; no se insiste |
| **Autocasion** | No se puede leer: el propio robots.txt devuelve 403 | — | — | **Bloqueado**: desafío de Cloudflare ("Just a moment…"). Registrado; no se insiste |

Hallazgo técnico: `urllib.robotparser` (biblioteca estándar) no soporta comodines. En coches.net dejaba pasar `?pg=8`, que está prohibido, y bloqueaba rutas permitidas. Se ha sustituido por `src/robots.py`.

---

# Fase 0-bis — Plataformas profesionales con garantía (2026-10-31)

Las mismas reglas: robots.txt con `src/robots.py` (RFC 9309), pausas de 2–5 s, caché en `raw/` y ningún intento de saltar bloqueos. Playwright solo se ha usado en las webs que pintan el stock con JS, con una carga por URL (`tools/render_probe.py`).

| Plataforma | robots.txt | Datos | ¿Opera en Valencia? | Stock ≤ 4.600 € | Decisión |
|---|---|---|---|---|---|
| **OcasionPlus** | Prohíbe filtros por parámetro (`?price_max`, `?marca`, `?sort`, `?location`…). Permite `/coches-segunda-mano/{ciudad}`, `?page=N` y las fichas | Listado: JSON-LD `ItemList` (20 por página). Ficha: objeto `vehicle` en el payload RSC con `price.cash` / `price.withFinancing`, `owners`, `maintenanceBook`, `itv.validDate`, `warranty.dealer` (meses) y `warranty.price` (ampliación). En el texto: "Transferencia y preparación no incluida: N €", revisión de 200 puntos, "Certificado kilómetros reales", 15 días o 1.000 km de prueba | Sí: Valencia, Alzira, Dénia… (851 coches; el más barato, 1.490 €) | **Sí** | **Implementar** (recorrido completo de `/valencia?page=N`) |
| **Flexicar** | Prohíbe `/api/`, `/search/` y `?utm`. Permite rutas y parámetros de filtro | `__NEXT_DATA__` → `initialVehicles`: `price` (financiado), `cashPrice`, `financingConditions`, `ecoSticker`, concesionario | Sí (1.193 coches en la provincia) | **No**: `?priceTo=4600` da 0. El más barato está a 5.990 € financiado (7.490 € al contado) | Implementada como **vigilancia** con el filtro del servidor |
| **Clicars** | Muy permisivo | HTML con fichas; precio al contado y financiado; `?order=price.asc` | Vende online a toda España, con entrega | **No**: el más barato, 7.290 € al contado (6.690 € financiado) | **Vigilancia** (primera página ordenada por precio) |
| **Autohero** | Prohíbe checkout, myhero, inspección… Permite `/es/search/` | `window.__APOLLO_STATE__` → `searchAdV9AdsV2` con `offerPrice` y `financedPrice`; acepta `?priceMax=` y `?sort=PRICE_ASC` | Entrega a toda España (página `/ubicaciones/valencia/`) | **No**: `priceMax=5000` da 0; el más barato de España está a 6.699 € | **Vigilancia** |
| **Renew (Renault/Dacia)** | Prohíbe `conf`, `dealerId`, `modelURI` y `vin` | `window.APP_STATE` con 23 coches por página; facets con el precio mínimo; `warrantyInfo` (Start 12 meses, Gold 24) | Sí (concesionarios en Gandia y Valencia) | **No**: el más barato de España está a 6.990 € (`prices.customerDisplayPrice_min`) | **Vigilancia** (lee el mínimo de los facets) |
| **Toyota Ocasión** | Permisivo en toyota.es; la API `usc-webcomponents.toyota-europe.com` no tiene robots.txt | JSON de la API con garantía (p. ej. 45 meses), historial y precio con IVA. Filtros y paginación no documentados: los parámetros probados dan 404 | Sí (3.470 coches en España) | No comprobable sin interactuar con la web; la garantía es de 24 meses o más | **No implementada** (sin forzar). Los concesionarios Toyota de Valencia también publican en AutoScout24 y Coches.net |
| **Hyundai Promise** | hyundai.es no tiene robots.txt | Tienda HTML (`/seminuevos/index.php?route=product/vehiculo…`) con precio al contado y cuota | Sí (4 coches en Valencia) | **No**: el programa admite hasta 5 años (Approved, hasta 8 años o 160.000 km) y los i30 de Valencia son de 2023 o posteriores, desde 13.000 € | Registrada, no implementada |
| **Kia Seminuevos Certificados** | Permisivo | Página informativa sin stock central; solo enlaza al buscador de concesionarios | — | No hay stock central | Registrada |
| **Mazda Selected** | mazdaselected.es redirige a mazda.es | Página informativa sin listado de stock | — | No hay stock central | Registrada |
| **Honda** | — | No se ha encontrado programa oficial de ocasión en España | — | — | Descartada |
| **Das WeltAuto** | `User-agent: *` / `Disallow: /`: solo permite los bots que nombra | — | — | — | **Excluida por robots.txt** |
| **Spoticar** | El propio robots.txt devuelve 403 (Akamai, "Access Denied") | — | — | — | **Bloqueada**; registrada |

Notas:
- El detector de bloqueos daba un falso positivo en Autohero, que carga el SDK de captcha de AWS WAF pero sirve la página. Ahora solo cuentan los códigos 403/405/429/503, los títulos de páginas de desafío o los marcadores en páginas pequeñas.
- Garantía legal en usados de vendedor profesional: ver `fiscal.yaml` → `garantia_legal`.

---

# Implementación y validación con anuncios reales (31-10-2026)

| Fuente | Peticiones por ejecución | Resultado de la primera ejecución | Notas |
|---|---|---|---|
| OcasionPlus | unas 43 páginas de listado + 1 ficha por candidato | 10 anuncios ≤ 4.600 € (en el listado) en la provincia | Ficha completa: contado/financiado, garantía incluida (meses) y precio de la ampliación, 350 € de transferencia y preparación, 200 puntos, km certificados, 15 días o 1.000 km, propietarios, ITV, libro. Varios anuncios **solo valen financiando** (p. ej. Dacia Logan: 2.500 € financiado frente a 7.990 € al contado) |
| Flexicar / Clicars / Autohero / Renew | 1–2 | 0 en el rango | Vigilancia con el filtro de precio del servidor |
| AutoScout24 | 1 por marca + 1 ficha por anuncio | 29 anuncios (≤ 4.600 €, 50 km, 2008 o posterior, ≤ 220.000 km) | Comprobado que los 0 resultados son reales (p. ej. el Renault más barato del radio cuesta 4.990 €). La garantía viene como texto ("12 mes"); el "precio al contado" a veces solo aparece en la descripción → `extract_pro_signals` |
| Coches.net | 1–6 por modelo + 1 ficha por candidato | ver `muestras.md` | **Cobertura parcial** en los modelos con más de 6 páginas en Valencia (Ibiza, León, Golf, Corsa, Mégane…): robots.txt prohíbe `pg≥7` y cualquier filtro u orden por parámetro. Queda registrado en cada ejecución |
| Wallapop | 1 por modelo + 1 ficha por candidato | 80 anuncios | Solo rutas permitidas (`/coches-segunda-mano/{modelo}/valencia` y `/item/`). La página de modelo da unos 80 anuncios cercanos sin paginar, así que la cobertura también es parcial. `itemSeller.type` = `professional` / `normal` |

Otros hallazgos:
- `urllib.robotparser` no sirve para estos robots.txt (sin comodines); se usa `src/robots.py`.
- La distancia se calcula con GeoNames (CP o municipio → coordenadas) y se descartan los anuncios a más de `radio_km`. Ejemplo: Gandía, a unos 58 km.

---

# Ampliación de cobertura (31-10-2026, tarde)

- **Radio de 70 km y año mínimo 2006** (configurables). En Coches.net se recorren las provincias que toca el radio
  (`ubicacion.provincias_cochesnet`: valencia, castellon).
- **Coches.net**: para cada provincia, la ruta **por marca** (`/{marca}/segunda-mano/{provincia}/`) y la ruta
  **por modelo** (`/{marca}/{modelo}/segunda-mano/{provincia}/`), cada una hasta `pg=6`, deduplicando por ID. La ruta por
  marca usa otro orden de relevancia y deja ver anuncios de modelos que en su propia ruta pasan de 6 páginas.
  Comprobado: `/seat/segunda-mano/castellon/` → provincia 12, 137 anuncios.
- **Wallapop**: existen las rutas de modelo por municipio (`/coches-segunda-mano/{modelo}/{municipio}`) para Torrent,
  Paterna, Sagunto, Gandía, Burjassot y Manises (comprobado con Seat Ibiza: 5, 22, 13, 14, 1 y 1 anuncios). Están
  permitidas por robots.txt (sin `?`). Solo se consultan cuando la página de València de ese modelo viene llena
  (≥ `fuentes.wallapop.saturacion`, 75), para no multiplicar las peticiones por 7.
- **Modelos añadidos** (con dato de fiabilidad ADAC/TÜV/OCU o carrocería que ahora se admite con penalización): Audi A1/A3,
  MINI, Mercedes Clase A/B, smart, Opel Adam/Karl/Meriva, Renault Twingo/Fluence, Skoda Rapid, Seat Toledo, VW Beetle/Jetta,
  Ford B-Max/Fusion, Hyundai ix20, Kia Venga, Citroën C3 Picasso, Peugeot 301, Toyota Avensis…
  Los monovolúmenes grandes (Zafira, Scénic, Touran, C-Max, Xsara/C4 Picasso, Verso) se reconocen para excluirlos.

## Fuentes de fiabilidad de motores diésel
Verificado leyendo el artículo original (robots.txt de largus.fr lo permite):
**L'argus, «Diesel : la liste des pannes récurrentes des moteurs HDi, dCi, TDI…», 28-10-2014**, págs. 2–5.
| Motor | Problema (según la fuente) | Años |
|---|---|---|
| PSA 1.6 HDi 16v (= Ford 1.6 TDCi) | Inyectores, volante motor, turbo, embrague | hasta 2010 |
| PSA 1.6 HDi 8v | Inyectores Continental (tirones) hasta 04-2014; la polea del cigüeñal desgasta la correa | 2010–2014 |
| PSA 1.4 HDi (= Ford 1.4 TDCi) | Fugas de inyectores (juntas hasta 04-2004, tubos hasta 01-2008); FAP Euro 5 hasta 07-2013 | 2001–2013 |
| Renault 1.5 dCi (K9K) | Cojinetes de biela con desgaste anormal y riesgo de rotura (cerca del 1 %) | hasta 2007 |
| Fiat 1.3 JTD/Multijet (también Ford Ka, Suzuki Splash/Swift) | Riesgo de rotura por dilución del aceite | — |
| Opel 1.3 CDTI | Soportes/juntas de inyectores (olor a gasóleo) | hasta 06-2009 |
| VW 1.6 TDI (common rail) | Fuga de refrigerante por la bomba de agua | — |

Además: campaña EA189 (dieselgate) del 1.2/1.6/2.0 TDI (autofacil.es, motor.es) y garantía de 8 años del depósito
AdBlue de los BlueHDi de Stellantis (nota de prensa de la OCU, 27-12-2024).
**PENDIENTES** (sin fuente seria): 1.2/1.4 TDI de 3 cilindros (más allá de la campaña), Opel 1.7/1.6 CDTi, Toyota 1.4 D-4D,
Hyundai/Kia CRDi y Suzuki 1.3 DDiS. Entran con la fiabilidad limitada a neutra (`filtros.diesel.sin_fuente: penalizar`).

## Perfil mercado (01-11-2026)

| Fuente | Qué permite robots.txt | Qué se usa | Cobertura |
|---|---|---|---|
| Coches.net | Prohíbe `pg>=7`, `MaxPrice`/`MinPrice` y `/Detail/` | `/segunda-mano/{prov}/`, `/{marca}/segunda-mano/{prov}/`, `/{marca}/{modelo}/segunda-mano/{prov}/`, `/km-0/{prov}/`, `/nuevos/{prov}/` | Valencia: 15.852 usados, 104 km 0. Nuevos: 7.313 en toda España, de los que solo son visibles 180. Las marcas compuestas pueden usar guion bajo (`alfa_romeo`). Si una ruta no aplica el filtro, devuelve el listado general y se descarta. |
| AutoScout24 | Prohíbe `/lst?` y `/lst/?`; permite `/lst/{marca}?…` | `zip`, `zipr`, `ustate=N,U` y `pricefrom`/`priceto` | Hasta 20 páginas de 20 anuncios por búsqueda. Se trocea por precio y se filtra por el prefijo del código postal. |
| OcasionPlus | Prohíbe los filtros por parámetro | `/coches-segunda-mano/valencia?page=N` (`vehicleList` del payload RSC) | Todo el stock de Valencia (unos 830 coches). |
| Flexicar | Prohíbe `/api/` | Solo la primera página; `?page=` se ignora | 12 de unos 1.183 coches. |
| Webs de marca | — | Ninguna | Das WeltAuto: Disallow total. Spoticar: 403. Toyota: sin paginación documentada. Hyundai Promise: 4 coches. Kia y Mazda: sin stock central. |
