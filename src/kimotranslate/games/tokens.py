"""Tokens protegidos genéricos: {var}, %s/%d, \\n, <tag>, [cmd].

Estrategia: el texto viaja al proveedor CON sus tokens intactos (cortos y
normalmente preservados) + instrucción de preservación en el prompt MAGI.
Antes de exportar se valida igualdad de multiset; si difiere, la línea va a
REVIEW_REQUIRED y no se exporta. Sin reemplazos ciegos, sin máscaras que el
MT pueda corromper.
"""

from __future__ import annotations

import re

_PATTERNS = [
    r"\{[^{}]*\}",  # {PLAYER_NAME}, {0}
    r"%[sd]",  # %s, %d
    r"\\[nrt\\]",  # \n literales del script
    r"<[^<>]*>",  # <control>
    r"\[[^\[\]]*\]",  # [command]
    r"＄[^＄]*＄",  # full-width vars (YU-RIS suele usar $variables)
    r"\$[A-Za-z_][A-Za-z0-9_]*",
]

_RX = re.compile("|".join(f"(?:{p})" for p in _PATTERNS))


def find_tokens(text: str) -> list[str]:
    return _RX.findall(text)


def tokens_ok(original: str, exported: str) -> bool:
    """Igualdad estricta de multiset: el engine necesita cada token."""
    from collections import Counter

    return Counter(find_tokens(original)) == Counter(find_tokens(exported))
