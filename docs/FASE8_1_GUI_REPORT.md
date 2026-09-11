# FASE 8.1 — GUI Report (0.8.1)

## Resultado: PARTIAL

UI reescrita sobre CustomTkinter con backend intacto. Lógica + API verificadas
aquí; render real pendiente de Windows (sin display/tkinter en este entorno).

## Antes vs después

Antes: ventanas ttk sueltas por pestañas, sin tema, sin jerarquía, errores
crudos, operaciones bloqueantes, sin estados. Después: shell sidebar/topbar/
status, tema dark centralizado, cards, stepper por juego, biblioteca de
imágenes, review con prev/next, jobs con retry, editor rediseñado, toasts,
todo no-bloqueante.

## Pantallas

Dashboard (contadores + proyecto activo + actividad), Games (cards + Open/
Extract/Translate), Game Detail (stepper + 6 tabs + acciones con jerarquía),
Translate (provider/modelo/game + jobs recientes), Images (filtros+búsqueda+
lazy + abrir editor), Review (prev/next, filtros, Save/Validate/Reject/terms),
Jobs (filtros + retry solo FAILED), Datasets (build), Settings (categorías +
providers Configured ✓ + updates), Editor (canvas zoom/pan/handles/máscara/
propiedades/undo/redo/preview/validate).

## Tests

| Suite | Resultado |
|---|---|
| KimoTranslate | 119 passed (9 GUI: tema, cliente, retry, registry, editor-API, URLs, versión) |
| Hub | 165 passed (sin cambios) |
| MAGI | 21 passed (sin cambios) |
| ruff | limpio |
| compile | `py_compile` 20 ficheros GUI OK |
| Windows smoke | PENDING (checklist: startup, sidebar, 9 vistas, editor, atajos, 100/125/150%, 1920×1080) |

## Dependencias

* `customtkinter` (MIT): base visual. Instalación dev/build Windows; bundlado.
* `TKinterModernThemes` evaluado y **descartado**: segundo framework visual =
  inconsistencia + interop no verificable; CTk cubre tema/widgets/HiDPI.
* Sin iconos/graficas/animaciones nuevas (texto + símbolos unicode).

## Problemas encontrados

| Problema | Causa | Solución | Estado |
|---|---|---|---|
| Métodos duplicados en client.py | edición por bloques | deduplicado | cerrado |
| `export-list` capturada por `{image_id}` | orden rutas (fase 6) | ya corregido antes | cerrado |
| `KimoApiClient` sin métodos batch usados por vistas | cliente escrito antes que vistas | añadidos | cerrado |
| `metrics.request` ausente para retry | JobResultOut sin métricas | campo aditivo `metrics.request` | cerrado |
| Sin tkinter en Pi | entorno | py_compile + tests lógica + checklist Windows | documentado |

## Limitaciones

* Bug: render visual no inspeccionado aquí (PENDING Windows).
* Known: thumbnails = subsample entero (sin PIL en GUI); 100s de imágenes OK
  por lazy loading, pero sin virtualización real.
* Known: worker status = heurística (jobs RUNNING → BUSY) sin endpoint propio.
* Future: light mode existe en tokens pero CTk aplica el suyo; afinar si choca.
* Future: iconos propios, i18n, atajo Middle-drag pan.

## Archivos

Nuevos: `gui/{client,app.py}`, `gui/theme/*`, `gui/components/*`,
`gui/views/*`, `gui/editor/editor.py`, `tests/test_gui.py`.
Movidos: `gui/tkinter/app.py` (launcher fino), `gui/legacy/*` (referencia).
Modificados: `__init__.py` + `pyproject.toml` (0.8.1), `api/schemas|router`
(`metrics.request` aditivo), `translate/pipeline` (pasa metrics),
`KimoTranslate.spec` (datas gui + customtkinter), `build_windows_gui.ps1`,
README.
Backend: 0 cambios de lógica (1 campo aditivo).
