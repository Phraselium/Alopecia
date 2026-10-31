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
