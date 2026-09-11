"""Orden de lectura + agrupación de regiones. Heurísticas, sin ML."""

from __future__ import annotations


def reading_order(regions: list[dict]) -> list[dict]:
    """Horizontal: filas por y, izquierda->derecha. Vertical: columnas
    derecha->izquierda, arriba->abajo (japonés tategaki)."""
    out = []
    for r in regions:
        out.append(r)
    horiz = [r for r in out if r.get("orientation", "horizontal") == "horizontal"]
    vert = [r for r in out if r.get("orientation") == "vertical"]
    horiz.sort(key=lambda r: (r["y"] // max(1, r["h"] // 2), r["x"]))
    vert.sort(key=lambda r: (-r["x"], r["y"]))
    ordered = horiz + vert
    for i, r in enumerate(ordered):
        r["reading_order"] = i
    return ordered


def group_regions(regions: list[dict], gap_factor: float = 0.6) -> list[dict]:
    """Agrupa fragmentos próximos y alineados (misma caja de diálogo).
    group_id = img:{image_id}:g{n}. Sin grupo -> grupo propio."""
    groups: list[list] = []
    for r in sorted(regions, key=lambda r: r.get("reading_order", 0)):
        placed = False
        for g in groups:
            last = g[-1]
            if _compatible(last, r, gap_factor):
                g.append(r)
                placed = True
                break
        if not placed:
            groups.append([r])
    img = regions[0]["image_id"] if regions else "img"
    for n, g in enumerate(groups):
        gid = f"img:{img}:g{n}" if len(g) > 1 else ""
        for r in g:
            r["group_id"] = gid
    return regions


def _compatible(a: dict, b: dict, gap_factor: float) -> bool:
    if a.get("orientation") != b.get("orientation"):
        return False
    if a.get("orientation") == "vertical":
        gap = a["x"] - (b["x"] + b["w"])
        aligned = abs(a["y"] - b["y"]) < max(a["h"], b["h"]) * 0.5
        return 0 <= gap <= max(a["w"], b["w"]) * gap_factor and aligned
    gap = b["y"] - (a["y"] + a["h"])
    aligned = abs(a["x"] - b["x"]) < max(a["w"], b["w"]) * 0.5
    return 0 <= gap <= max(a["h"], b["h"]) * gap_factor and aligned
