"""Inpainting sencillo y robusto (mediana por anillos, numpy).

NO es IA: rellena desde el borde conocido hacia dentro. Suficiente para
bocadillos y UI sobre fondos simples. AI inpainting = trabajo futuro con la
misma interfaz ImageInpainter.
"""

from __future__ import annotations

from typing import Protocol

INPAINT_VERSION = "simple-median@1"


class ImageInpainter(Protocol):
    def inpaint(self, image, mask) -> object:
        """image/mask PIL. Devuelve PIL.Image RGB(A) del mismo tamaño."""
        ...


class SimpleInpainter:
    def inpaint(self, image, mask):
        import numpy as np

        arr = np.asarray(image.convert("RGB")).astype(float)
        m = np.asarray(mask.convert("L")) > 127
        if not m.any():
            return image.convert("RGB")
        return self._fill(arr, ~m, m)

    def _fill(self, arr, known, missing):
        import numpy as np
        from PIL import Image

        filled = arr.copy()
        todo = missing.copy()
        h, w = todo.shape
        while todo.any():
            # píxeles missing con al menos un vecino conocido (4-conectado)
            k = ~todo
            up = np.zeros_like(todo)
            up[1:] = k[:-1]
            down = np.zeros_like(todo)
            down[:-1] = k[1:]
            left = np.zeros_like(todo)
            left[:, 1:] = k[:, :-1]
            right = np.zeros_like(todo)
            right[:, :-1] = k[:, 1:]
            edge = todo & (up | down | left | right)
            if not edge.any():  # isla sin borde conocido: media global
                for c in range(3):
                    filled[:, :, c][todo] = filled[:, :, c][~todo].mean()
                break
            ys, xs = np.nonzero(edge)
            for y, x in zip(ys.tolist(), xs.tolist(), strict=True):
                vals = []
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < h and 0 <= xx < w and not todo[yy, xx]:
                        vals.append(filled[yy, xx])
                if vals:
                    filled[y, x] = np.median(vals, axis=0)
                    todo[y, x] = False
        return Image.fromarray(np.clip(filled, 0, 255).astype("uint8"))
