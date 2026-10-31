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
