"""KimoTranslate: localización de juegos antiguos de Windows.

Arquitectura: GUI Windows (Tkinter) -> Server Raspberry Pi (API + Jobs +
Translation Knowledge Core) -> Worker (MAGI, Ollama, OCR).
Fase 1: skeleton sin inferencia pesada.
"""

__version__ = "0.8.0"  # única fuente: GUI, release manifest y updater la usan
