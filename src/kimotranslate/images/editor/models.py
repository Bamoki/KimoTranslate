"""Modelo de operaciones del editor. Cada op guarda before/after para Undo."""

from __future__ import annotations

from dataclasses import dataclass, field

# Tipos de operación con historial.
MOVE = "move"
RESIZE = "resize"
CREATE = "create"
DELETE = "delete"
EDIT_OCR = "edit_ocr"
EDIT_TRANSLATION = "edit_translation"
SET_STYLE = "set_style"
MASK_STROKE = "mask_stroke"
VALIDATE_REGION = "validate_region"


@dataclass(frozen=True)
class EditOp:
    id: str
    image_id: str
    op_type: str
    target_id: str  # region_id o "" (imagen)
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    created_at: str = ""
    undone: bool = False
