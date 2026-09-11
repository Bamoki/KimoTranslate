# KimoTranslate — Arquitectura (Fase 7)

## 1. Editor visual: estado en servidor, canvas delgado

`images/editor/` (models/history/operations/service) + API; Tkinter solo
HTTP+PhotoImage (sin PIL/OCR/SQLite en GUI). Ops geométricas y de texto
persisten por llamada + historial `image_edits` (before/after) con undo/redo.
Traducción editada -> Correction Fase 4 -> Validate -> TM/ejemplo (nunca
directo a TM). Máscara = strokes vectoriales (add/erase) sobre automática
(`mask_source/mask_modified/mask_version`); rasteriza el localize (server y
worker comparten `rasterize()`). Preview server-side (con fichero) o job
LOCALIZE_IMAGE; parcial por `region_ids` sobre background cacheado.
Dirty flags por hash (translation/mask/inpaint/render/ocr); versiones
`localized_prev.png` + Reset Region/Image; `original.png` jamás se toca.

## 2. Fases 1-6 (resumen)

F1 skeleton; F2 Hub autoridad + MAGI sin Committee; F3 providers + terms +
TM; F4 corrección->dataset; F5 YU-RIS (cp932 sin acentos); F6 imágenes
(OCR mock+tradujap, mask/inpaint/render, DejaVu, cache y manifest).

## 3. Fase 8

OCR japonés real con modelos Tradujap en worker, fuente CJK vertical,
inpaint IA opcional, batch masivo de imágenes.

## 1. Imágenes: OCR -> traducción -> máscara -> inpaint -> render

```text
discover (heurísticas, nunca borra) -> OCR_IMAGE (Hub, worker)
  -> regiones (orden lectura JP h/v + grupos) -> pipeline TEXTO existente
  (content_type=image_text, scope=game, prev/next por orden)
  -> sync -> corrections (image_region_id) -> validate -> TM/ejemplo
  -> LOCALIZE_IMAGE (Hub, worker) -> mask + inpaint + render -> artefactos
  -> EXPORT_GAME incluye localized (loose override + backup)
```

Sin sistemas nuevos: jobs/workers Hub, pipeline/cache/TM/terms/corrections
reutilizados, tokens de Fase 5 (`{var} %s \n <tag> [cmd] $var`) validados en
sync y localize (mismatch = REVIEW_REQUIRED / línea excluida).

## 2. OCR

`ImageOcrEngine.detect_text()` (PIL) -> regiones+bbox+confianza+orientación.
Motores: `mock` (determinista, tests) y `tradujap` (adapter a
`detect_blocks` + `build_engine` de Tradujap: paddle/manga-ocr/surya en el
worker con GPU; sin Tradujap/modelos = error claro). Sin Committee nuevo.

## 3. Inpaint/render (PIL+numpy, DejaVu vendored)

Máscara bbox+padding/polígono; inpaint mediana-por-anillos (IA = futuro tras
el Protocol); renderer con wrap/shrink (FIT/SHRUNK/OVERFLOW), stroke,
vertical apilado, y **glyph validation real (parse cmap TTF)** -> RENDER_FAILED
antes que imagen rota. Español completo con DejaVu; japonés vertical necesita
fuente CJK vía `KIMOTRANSLATE_FONT_PATH` (documentado, testeado el fallo honesto).

## 4. Cache y artefactos

Clave = hash(imagen+ocr+config+traducciones+renderer+inpaint) en el manifest;
`images/{id}/`: original/ocr.json/translation.json/mask/manifest.json/localized.
ImageManifest con versiones, conteos, timings (ocr/translation/inpaint/render).

## 5. Fases 1-5 (resumen)

F1 skeleton; F2 Hub autoridad + MAGI sin Committee; F3 providers + terms +
TM; F4 corrección->dataset; F5 YU-RIS extract/export (cp932 sin acentos).

## 6. Fase 7

Editor visual de regiones (mover/resize/refuente), OCR japonés real en worker
con modelos Tradujap, SJIS-tunneling/fuente ES para YU-RIS.

## 1. Juegos ClockUp / YU-RIS

Engine detectado: **YU-RIS** (Euphoria verificado en VNDB; el resto por
detector, nunca por nombre). Scripts `YSTB` (magic + header 32B + code/args/
recursos/offsets, XOR 4-byte por sección, cp932) sueltos en `ysbin/*.ybn` o
dentro de `ysbin.ypf` (magic `YPF\0`, entradas ofuscadas + zlib). Spec
implementada de extYuRis (open source) + notas VNTranslationTools.

Evidencia del detector: `yu-ris.exe`, `*.ypf`/`ysbin/`, `pac/`, magia YSTB
leída del fichero. Sin evidencia -> `unknown` (el extractor no lo toca).

Claves XOR por juego (defaults `0x96AC6FD3/0x6CFDDADB/0x30731B78` + auto-guess
por nulos del descriptor); opcodes msg/call por guess estadístico (densidad
JP / firma `"es...*`) y guardados por fichero en el manifest (sin ellos no
hay repack). YSCM/YSER/etc no son escenario y se ignoran.

## 2. Límites honestos del formato

* **cp932 no acepta ni un acento español** (áéíóúñ¿¡ todos fallan): el
  exportador valida encoding por línea (FAILED + motivo, original intacto).
  Español con acentos necesita SJIS-tunneling o fuente custom (futuro).
* Speaker = heurística (último `es.char.name*`); narration sin señal fiable
  (no se inventa tipo).
* Export = loose-file override (el runtime prefiere sueltos; sin repack YPF).

## 3. Flujo

```text
POST /games (detect) -> POST /games/{id}/extract (local o job EXTRACT_GAME Hub)
  -> worker extrae (suelto o .ypf) -> bulk por ID estable -> NEW/CHANGED/UNCHANGED/REMOVED
POST /games/{id}/translate -> fan-out TRANSLATE_TEXT (pipeline: cache(scope=game)+TM+terms)
POST /games/{id}/sync -> Hub results -> TRANSLATED o REVIEW_REQUIRED (tokens)
Review tab -> corrections (game_text_id) -> validate -> game VALIDATED + TM + ejemplo
POST /games/{id}/export (local o job EXPORT_GAME Hub) -> backup + tmp + re-parse + rename
```

Tokens (`{var} %s \n <tag> [cmd] $var`) viajan intactos al proveedor y se
validan por multiset en sync y export; mismatch bloquea la línea/fichero.
IDs `clockup:{game}:{relpath}:msg:{slot}` deterministas; re-extracción no
duplica ni borra traducciones. Cache key lleva scope=game_id (A≠B).

## 4. Fases 1-4 (resumen)

F1 skeleton; F2 Hub autoridad jobs/workers, MAGI sin Committee; F3
multi-provider + terminología game>project>global + TM MAGI; F4
corrección->validación->TM/ejemplos->dataset JSONL.

## 5. Fase 6

OCR en imágenes (reutilizar Tradujap), inpaint, editor visual. Prohibido:
fine-tuning, universal engines, tocar ejecutables.

## 1. Ciclo de aprendizaje

```text
Provider -> machine result -> POST /corrections (generated/reviewed/corrected)
  -> PATCH validate -> VALIDATED -> TM (dedup) + training_example (quality 1.0)
  -> POST /datasets/build (filtros) -> JSONL versionado + sha
Terminología: solo manual (GUI "To terminology" -> POST /terminology).
```

Estados generated->reviewed->corrected->validated|rejected; validated terminal.
Calidad: humano manda (validated 1.0 > corrected 0.7 > reviewed 0.5 >
generated/confianza auto). TM: misma fuente+traducción+contexto no duplica;
conflictos se conservan, gana score > proyecto > confianza > primera validada.
`memory.db` respeta `settings.data_dir` (KIMOTRANSLATE_MEMORY_DB override).

## 2. Fases 1-3 (resumen)

F1: skeleton API+SQLite+Tkinter. F2: Hub única autoridad jobs/workers
(`method=custom`, claim excluye custom sin `?types=`); MAGI vía OllamaClient+
PromptSpec (sin Committee financiero). F3: providers magi|ollama|deepl|google
mismo Protocol; terminología game>project>global; TM MAGI Memory con tags
(validated, content_type, project:) y umbral 0.85.

## 3. Fase 5

Export/parcheo de juegos (BUILD_DATASET pasa al Hub si crece; JobType listo).

## 1. Flujo

```text
POST /translations {provider}
  -> exact cache HIT? devuelve (sin job, sin proveedor)
  -> TM find_reusable (score>=0.85, domain+content_type+project)? devuelve memory_hit
  -> MISS: job method=custom domain=translation al Hub
Worker claim types=translation:
  -> lee términos (API Kimo) + candidatas TM (API Kimo)
  -> reutilizable? COMPLETED memory_hit (sin proveedor)
  -> engine = get_engine(provider): magi|ollama|deepl|google
  -> MAGI recibe glosario+ejemplos en el prompt (contexto, no sustitución)
  -> Hub result; Kimo GET /jobs/{id} escribe exact cache
```

## 2. Proveedores (`engines/`)

Mismo `Protocol translate(request, glossary, examples) -> TranslationResponse`
normalizado (translation, provider, model, langs, cached, memory_hit,
duration_s, confidence opcional, metadata). La API depende del Protocol.

* `magi_engine.py`: OllamaClient + PromptSpec `kimotranslate.translate@v1` +
  `KimoTranslateAdapter`. `provider=ollama` = misma clase (MAGI ya habla
  Ollama). Sin Committee (normalización financiera incompatible, ver Fase 2).
* `http_base.py`: política única timeout/429/5xx->retry+backoff, 4xx->fail,
  claves redactadas en errores.
* `deepl.py` (v2, `DEEPL_GLOSSARY_ID` opcional), `google.py` (v2, sin
  glosarios: metadata, sin reemplazos ciegos). Claves solo en el worker.
* `MockEngine` sigue para tests de arquitectura.

## 3. Terminología (`knowledge/terminology.py`, tabla en .db de Kimo)

`term/preferred/langs/project_id/game_id/priority/notes`.
Precedencia juego > proyecto > global; a igual nivel mayor priority.
`lookup` devuelve la ganadora; el worker inyecta `term = preferred` al
prompt MAGI. Externos: solo glosario oficial configurado.

## 4. TM (`knowledge/memory.py`: MAGI Memory, cero código propio)

`MemoryStore` (fichero `memory.db` compartido en la Pi) + retriever
configurable (default `keyword`: offline, sin descargas). Filtros por tags:
`validated` obligatorio, `content_type` y `project:` compatibles, `domain`
exigido (sin domain no hay búsqueda). Score SequenceMatcher + umbral.
`add()` solo para entradas validadas (correcciones); lo auto nunca entra.
Tradujap usará el mismo fichero/API en Fase 4.

## 5. Sin cambios en el Hub en Fase 3. Confirmado: sin 2º queue/registry/
stale/memory. Tests: `tests/test_fase3.py` (17) + fases 1-2 intactas.

## 6. Fase 4

Correcciones humanas -> TM/terminología/dataset; `source_app` compartido con
Tradujap; export/parcheo de juegos. Prohibido: OCR, inpaint, extractores.

## 1. Principio: el Hub manda

```text
Windows GUI (solo HTTP)
     │ POST /translations
     ▼
KimoTranslate :8005 ── TranslationService (cache + HubClient)
     │ jobs method=custom domain=translation
     ▼
Raspberry-Hub: ÚNICA autoridad de jobs, workers, heartbeat, claim,
progress, result, stale sweep, requeue. Kimo no tiene nada de eso.
     │ claim ?types=translation
     ▼
KimoWorker -> MagiTranslationEngine -> MAGI (Ollama) -> Hub result
     ▼
Kimo GET /jobs/{id}: COMPLETED -> lazy cache write -> GUI
```

**Confirmado por test**: `sqlite_master` de Kimo no tiene tablas jobs/workers;
`kimotranslate.jobs.manager` no existe; `claim/heartbeat` no existen en Kimo.

## 2. Cambios en el Hub (4 líneas, compatibles hacia atrás)

`backend/app/api/training.py` + `training/models.py`:

1. `method="custom"` aceptado (jobs no-entrenamiento). Nada existente lo usa.
2. `JobCreate.metrics` (dict libre): el request de traducción viaja en el job.
3. `claim` sin `?types=` **excluye** `method=custom`: `pc_worker` (sin filtro)
   jamás reclama un TRANSLATE_TEXT. Filtro explícito `types=translation`
   matchea por `domain`.
4. `POST /jobs/{id}/run` rechaza `custom` (el stub de training no debe tocarlos).

Hub verificado: 165 passed (suite completa menos `test_finetuning_real`).

## 3. MAGI: qué se reutiliza y qué no

* **Sí**: `OllamaClient` (transporte+retry+`json_mode`), `PromptSpec`
  (`kimotranslate.translate@v1`), `MemoryStore`/`retrieve_context` (opcional,
  `domain=game_translation`), `DomainAdapter` (`KimoTranslateAdapter`:
  `build_context/allowed_symbols/interpret_result`).
* **No**: `Committee` — su normalización es financiera (stances, symbols, echo
  gates) y corrompería JSON de traducción; 3 modelos por string = VRAM-thrash.
  Una llamada `generate + parse` es lo correcto. Documentado en el engine.
* **Nada copiado**: import directo de `magi`, error claro si falta.

`MagiTranslationEngine`: contexto (texto, langs, speaker, escena, prev/next,
relationship, tone, glosario, ejemplos memoria) -> prompt versionado ->
`generate(json_mode)` -> `{"translation", "confidence"}` -> memoriza en
MAGI Memory (tags `auto`, `content_type`). Backend `None` = Ollama real.

## 4. Cache

`normalize` (NFKC + colapsar espacios) -> `sha256(...|provider|model|
prompt_version|domain|content_type)` -> HIT devuelve sin tocar Hub/MAGI;
MISS crea job; `GET /jobs/{id}` COMPLETED escribe cache (una sola escritura,
un solo lugar). Segunda llamada idéntica: HIT, MAGI no ejecutado (test).

## 5. Contexto y dominios

`domain=game_translation` por defecto; `content_type` distingue
`vn_dialogue/game_ui/image_text` de `manga/novel`. La key del cache y la
memoria incluyen ambos: manga no contamina diálogo VN. Tradujap consumirá el
mismo Core por API en Fase 4 (sin importar DBs).

## 6. Seguridad LAN

Sin auth propia. Reutiliza `X-Worker-Key` y sesión admin del Hub solo si el
modo seguro está activo (env `HUB_*`, nunca hardcodeados, nunca en logs).
Sin JWT/OAuth/login de workers.

## 7. Ficheros

Kimo nuevos: `hub/client.py`, `engines/magi_engine.py`, `translate/pipeline.py`,
`jobs/types.py` (solo vocabulario), `tests/conftest.py`, `tests/test_fase2.py`.
Reescritos: `api/{app,router,schemas}.py`, `db/{repository,sqlite}.py`,
`worker/agent.py`, `gui/tkinter/app.py` (pestaña Translate), docs.
Borrados: `jobs/{manager,models}.py`, tablas jobs/workers, endpoints
`/workers/*`, `TranslationEngine` mock como default (sigue `MockEngine` para tests).

## 8. Fase 3

`TranslationEngine` DeepL/Google (mismo `Protocol`), terminología con
override por juego, TM vía MAGI `HybridRetriever` cableado al Core por API,
sweep visual en GUI. Prohibido: OCR real, inpaint/render, extractores,
fine-tuning.
