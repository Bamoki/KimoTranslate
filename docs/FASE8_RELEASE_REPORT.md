# FASE 8 — Release Candidate 0.8.0 (2026-09-09)

## Estado general: PARTIAL

Pipeline sintético completo y verificado. Juegos reales: **PENDING_REAL_GAME**
(los 3 ClockUp están en el PC Windows, inaccesible desde este entorno).
Nada fingido: lo real va marcado PENDING con scripts reproducibles.

## Tests

| Suite | Resultado |
|---|---|
| KimoTranslate | 99 passed |
| Raspberry-Hub | 165 passed |
| MAGI (core+memory) | 21 passed |
| Ruff check + format | limpio |
| GUI build (py_compile) | OK (Tkinter sin display aquí; checklist manual en README) |

## Juegos

| Juego | Detect | Extract | Translate | OCR | Localize | Export | Launch | Playable |
|---|---|---|---|---|---|---|---|---|
| ClockUp #1 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| ClockUp #2 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| ClockUp #3 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Sintético YU-RIS fiel | PASS | PASS | PASS | PASS | PASS | PASS | N/A | N/A |

Para cada juego real, ejecutar en Windows: `scripts/rc_validate_game.py <ruta>`
(nivel 0, solo lectura) y anotar engine/confidence/key/opcodes antes del nivel 1
(5–20 textos, 1–3 imágenes).

## Performance (sintético, Pi)

| Operación | Medida |
|---|---|
| extract 20 scripts / 120 textos | 0.01 s |
| cache-key por texto | 0.01 ms |
| TM score ×20 | 0.02 s |
| inpaint 800×600 (mediana pura) | 6.75 s |
| inpaint 320×120 (diálogo) | ~3 s |
| render región | ~12 ms |

## Problemas encontrados (todos cerrados)

| Problema | Causa | Solución |
|---|---|---|
| Flaky tests hub compartido | jobs viejos entre tests | diff por IDs en tests |
| Ruta `{image_id}` capturaba `export-list` | orden FastAPI | export-list antes |
| Fase5 stub sin `game_images_export_list` | export ampliado | stub + endpoint |
| `os.walk` no ordena: duplicado ganaba | orden FS | `dirnames.sort()` |
| `.notdef` falseaba glyph-check | getmask miente | parse cmap TTF real |
| `rasterize()` partió clase EditorService | indentación | movido a fin de fichero |
| Doble inpaint en preview | pipeline + llamada | una sola vía |
| Clave errónea → `struct.error` crudo | sin envolver | todo a `YstbError` |
| Hash cp932 con `replace` silencioso | enmascaraba | strict + marca `non-cp932-source` |
| YPF checksum sobre nombre cifrado | spec mal leída | checksum sobre descifrado |
| `í/á/ñ` no existen en cp932 | JIS real | validación por línea, doc |

## Limitaciones (known, no bugs)

* CP932 sin español acentuado; sin tunneling todavía.
* Export loose-override; sin repack YPF.
* Inpaint simple en fondos complejos; vertical JP básico + fuente CJK externa.
* OCR real sin verificar aquí (adapter existe, modelos en worker Windows).
* Speaker heurístico; `TRANSLATE_GAME` no existe (fan-out a TRANSLATE_TEXT basta).

## Archivos (Fase 8)

Creados: `games/integrity.py`, `release.py`, `scripts/rc_validate_game.py`,
`tests/test_fase8.py` (9), `docs/FASE8_RELEASE_REPORT.md`.
Modificados: `games/engines/clockup.py` (hash strict), `games/service.py`
(retry FAILED), `images/service.py` (retry FAILED), `core/config.py`
(`KIMOTRANSLATE_GAME_ROOTS`), `api/router.py` (`/integrity`, `/release`),
`gui/tkinter/app.py` (roots), README.

## Tests nuevos

`test_fase8.py`: sync idempotente, retry tras FAILED, OCR que explota (sin
escritura parcial), no secrets en jobs, integrity PASS/FAIL, release manifest,
YSTB/YPF edge, detector ignora basura.

## Decisiones

* Cero features nuevas: solo robustez + evidencia.
* Retry = sync marca FAILED + re-selección (sin reenviar QUEUED vivos).
* Integridad estricta (EXTRA_FILE también falla).
* `PLAYABILITY_PASS` solo en Windows con juego real; aquí `PIPELINE_PASS`
  sintético + `PENDING_REAL_GAME` explícito.
