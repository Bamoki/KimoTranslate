# KimoTranslate — Release Candidate 0.8.0

Localización completa de juegos antiguos de Windows (visual novels YU-RIS/ClockUp).
Texto extraíble + texto en imágenes. **Fase 8: RC validado sintéticamente.**

```text
Windows GUI (Tkinter) + Worker (traducción/OCR/imágenes)
  ⇄ HTTP
Raspberry Pi :8005 (API + SQLite) + Raspberry-Hub (jobs/workers, method=custom)
```

## Distribución Windows (.exe, sin Python)

```text
PC Windows: KimoTranslate.exe (solo GUI, sin Python)
  ⇄ HTTP (URL configurable en Settings)
Raspberry Pi :8005 (API) + Raspberry-Hub (jobs/workers/descargas)
```

### Instalar la GUI (usuario final)

1. En Raspberry-Hub: **Descargas → KimoTranslate → Descargar**.
2. Ejecuta `KimoTranslate.exe` (sin instalar nada).
3. En **Settings**, pon la URL del Hub (p. ej. `http://192.168.1.20:8005`) → Save.
4. Trabaja. Ante nueva versión, la GUI avisa (Actualizar / Ahora no).

### Construir el .exe (desarrollador, en Windows)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows_gui.ps1
# genera dist/KimoTranslate-0.8.0.exe + .sha256 (+ KimoTranslate-Updater.exe)
# publicar en el Hub (requiere admin):
powershell ... -Publish -HubUrl http://192.168.1.20:8000 -HubUser admin -HubPassword $env:HUB_PASS
```

Build con PyInstaller (solo build-time); la GUI es stdlib (tkinter+urllib).
Modo dev sin build: `python gui\tkinter\app.py`. Versión única:
`src/kimotranslate/__init__.py::__version__`. Build Windows no ejecutable
desde Linux/Pi (documentado; tests cubren manifest/checksum/updater).

### Autoactualización

Al iniciar (1/día máx, desactivable) o Settings → Buscar actualizaciones.
Descarga a temporal → verifica SHA-256 → cierra → `KimoTranslate-Updater.exe`
espera salida, re-verifica, backup `.bak`, reemplaza, lanza, limpia.
Checksum malo / fallo = instalación intacta + rollback. Nunca silenciosa.

### Rollback manual

Junto al .exe queda `KimoTranslate.exe.bak` tras actualizar: cierra la app,
borra el .exe actual y renombra el `.bak`. Versiones anteriores también en
Descargas del Hub.

### Troubleshooting distribución

| Síntoma | Causa |
|---|---|
| "servidor no disponible" | URL mal o Hub caído; la app no se cierra |
| update no aparece | misma versión o manifest inválido (ignorado, no rompe) |
| checksum mismatch | descarga corrupta; se conserva la instalación |
| updater ausente | modo dev: descarga verificada queda en temp |

## Instalación

```bash
# Pi: venv del Hub (fastapi/pytest/ruff) + pillow/numpy
/mnt/hdd/.../raspberry-Hub/.venv/bin/pip install pillow numpy
export PYTHONPATH=src
export KIMOTRANSLATE_DATA_DIR=/mnt/hdd/raspberry-hub/data/kimotranslate
export KIMOTRANSLATE_HUB_URL=http://127.0.0.1:8080
python -m uvicorn kimotranslate.api.app:app --port 8005
# Worker Windows (con Ollama/MAGI/Tradujap según motor):
set KIMOTRANSLATE_HUB_URL=http://<pi>:8080
python -m kimotranslate.worker.agent
# GUI Windows:
set KIMOTRANSLATE_SERVER_URL=http://<pi>:8005
set KIMOTRANSLATE_GAME_ROOTS=D:\Juegos;E:\VNs
python gui/tkinter/app.py
# MAGI: pip install -e ../magi (o PYTHONPATH). OCR tradujap: TRADUJAP_SERVER_SRC.
# Proveedores: DEEPL_API_KEY / GOOGLE_TRANSLATE_API_KEY solo en el worker.
```

## Uso

Detect → Extract → Translate → (Images: Discover → OCR → Translate) →
Review → Localize → Export → Integrity (`POST /games/{id}/integrity`) →
jugar. Análisis solo-lectura de un juego: `python scripts/rc_validate_game.py
"D:\Juegos\Euphoria"`. Release manifest: `GET /release`.

## Limitaciones conocidas

* **CP932 sin acentos españoles** (áéíóúñ¿¡ fallan; el exportador bloquea la
  línea, nunca sustituye en silencio). Tunneling/fuente custom = futuro.
* Export YU-RIS = loose override (sin repack YPF; el runtime prefiere sueltos).
* Inpaint simple: fondos complejos quedan mediocres (~7s en 800×600).
* Vertical JP necesita fuente CJK en worker (`KIMOTRANSLATE_FONT_PATH`).
* OCR real (manga-ocr/paddle) solo en worker con GPU + modelos Tradujap.
* Speaker = heurística (`es.char.name`); sin señal de narración fiable.

## Troubleshooting

| Síntoma | Causa probable |
|---|---|
| `unknown` en Detect | sin yu-ris.exe/ypf/ybn; variante no YU-RIS |
| 0 textos | opcodes no adivinados (fichero <3 líneas); usa hints vía re-extract |
| REVIEW_REQUIRED masivo | tokens destruidos por el proveedor; revisa glosario |
| OVERFLOW en render | caja pequeña; edita estilo o divide texto en editor |
| GLYPH_MISSING | fuente sin glyph; cambia `KIMOTRANSLATE_FONT_PATH` |
| export incompleto | líneas sin traducir o con tokens rotos (ver manifest.failed) |
| INTEGRITY_FAIL | backup ausente/modificado; no juegues ese output |
| worker no reclama | Hub caído o `types` sin `translation`; revisa `/health` |


```text
Juego -> discover imágenes -> OCR_IMAGE (Hub, worker) -> regiones
  -> pipeline texto (content_type=image_text) -> corrections
  -> LOCALIZE_IMAGE (Hub, worker) -> mask + inpaint + render -> localized.png
```

OCR: `mock` (tests) o `tradujap` (adapter a detect+paddle/manga-ocr en worker
con GPU; `KIMOTRANSLATE_OCR_ENGINE`, `TRADUJAP_SERVER_SRC`). Deps nuevas:
`pillow`, `numpy`. Fuente ES vendored (`assets/fonts`, override
`KIMOTRANSLATE_FONT_PATH` para CJK).

API imágenes: `POST /games/{id}/images/discover|bulk`, `GET /games/{id}/images`,
`POST .../{iid}/ocr|translate|sync|localize|bundle|artifacts`,
`POST .../images/ocr|translate|localize` (batch), `GET .../images/export-list`.
Artefactos en `{data_dir}/images/{id}/` (6 ficheros).

```text
Juego (yu-ris.exe + ysbin.ypf / ysbin/*.ybn)
  detect -> extract (suelto o .ypf) -> IDs estables -> pipeline (cache/TM/terms)
  -> sync -> corrections (game_text_id) -> validate -> export (backup+repack) 
```

Engine: YU-RIS (Euphoria verificado). Clave XOR y opcodes por juego en el
manifest. cp932: sin acentos españoles (validado por línea).
Ver `docs/ARCHITECTURE.md` (Fase 5) + `tests/game_factory.py` (fixtures).

API juegos: `POST /games/detect`, `POST/GET /games`, `POST /games/{id}/extract`
(local o job EXTRACT_GAME Hub), `GET /games/{id}/texts` (filtros),
`POST /games/{id}/translate|sync`, `POST /games/{id}/export`
(local o job EXPORT_GAME Hub), `GET /games/{id}/export-bundle`,
`POST /games/{id}/texts/bulk|export-report` (worker).

```text
GUI --POST /translations {provider}--> KimoTranslate :8005
  (exact cache -> TM -> Hub job)      Hub (jobs/workers, method=custom)
                                           | claim ?types=translation
                                      Worker --provider--> magi|ollama|deepl|google
```

## Arranque

```bash
export PYTHONPATH=src
export KIMOTRANSLATE_DATA_DIR=/mnt/hdd/raspberry-hub/data/kimotranslate
export KIMOTRANSLATE_HUB_URL=http://127.0.0.1:8080
python -m uvicorn kimotranslate.api.app:app --port 8005
KIMOTRANSLATE_SERVER_URL=http://<pi>:8005 python gui/tkinter/app.py
KIMOTRANSLATE_HUB_URL=http://<pi>:8080 KIMOTRANSLATE_WORKER_ID=w1 \
  python -m kimotranslate.worker.agent
```

MAGI: `pip install -e ../magi` (o `PYTHONPATH=.../magi/src`).

## Env (sin secretos en código/logs/jobs)

| Variable | Default | Uso |
|---|---|---|
| `KIMOTRANSLATE_DATA_DIR` | `./data` | SQLite + `memory.db` (MAGI schema, compartido) |
| `KIMOTRANSLATE_HUB_URL` | `http://127.0.0.1:8080` | Hub |
| `KIMOTRANSLATE_DEFAULT_PROVIDER` | `magi` | magi\|ollama\|deepl\|google |
| `KIMOTRANSLATE_MODEL` | `qwen2.5:7b` | Modelo magi/ollama en worker |
| `KIMOTRANSLATE_TM_THRESHOLD` | `0.85` | Reuso TM (server + worker) |
| `KIMOTRANSLATE_RETRIEVER` | `keyword` | keyword\|semantic\|hybrid (MAGI) |
| `KIMOTRANSLATE_EMBEDDINGS` | `fake` | fake\|local\|ollama (solo semantic/hybrid) |
| `KIMOTRANSLATE_MAX_RETRIES` | `3` | Retry proveedores externos |
| `DEEPL_API_KEY` / `DEEPL_API_URL` / `DEEPL_GLOSSARY_ID` | — | Solo en el worker |
| `GOOGLE_TRANSLATE_API_KEY` | — | Solo en el worker |

Glosarios oficiales: DeepL `glossary_id` si configurado (ver docs);
Google v2 no tiene: la terminología viaja como metadata, sin reemplazos ciegos.

## API

`POST /translations {text, provider, model?, context}` ·
`GET /jobs/{id}` · `GET /jobs` · `GET /providers` (sin claves) ·
`GET/POST /terminology` (scope game>project>global) ·
`GET /memory/search?query&domain&content_type&project_id` (sin domain = []).

Ver `docs/ARCHITECTURE.md`.
