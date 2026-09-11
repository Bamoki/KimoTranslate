"""Genera juegos ClockUp/YU-RIS sintéticos (texto ficticio) para tests.

Binarios válidos según spec extYuRis: YSTB con XOR + opcodes, YPF v<479.
Sin material comercial: todo texto inventado aquí.
"""

from __future__ import annotations

import os
import struct
import zlib
from binascii import crc32

MSG_OP = 0x5A
CALL_OP = 0x29
KEY_A = 0x96AC6FD3
KEY_B = 0x6CFDDADB


def _xor_block(data: bytearray, key: int, start: int, size: int) -> None:
    kb = struct.pack("<I", key)
    for i in range(size):
        data[start + i] ^= kb[i & 3]


def build_ystb(
    items: list, key: int = KEY_A, msg_op: int = MSG_OP, call_op: int = CALL_OP
) -> bytes:
    """items: ("msg", texto) | ("call", func, [textos]) | ("other", op)."""
    insts, args, res = [], [], bytearray()

    def typed_arg(text: str) -> None:
        raw = text.encode("cp932")
        args.append((0, 3, 3 + len(raw), len(res)))
        res.extend(struct.pack("<BH", 77, len(raw)) + raw)

    def raw_arg(text: str) -> None:
        raw = text.encode("cp932")
        args.append((0, 0, len(raw), len(res)))
        res.extend(raw)

    for it in items:
        if it[0] == "msg":
            insts.append((msg_op, 1))
            raw_arg(it[1])
        elif it[0] == "msg_raw":
            # bytes crudos (p. ej. controles inline reales \x80+byte)
            insts.append((msg_op, 1))
            args.append((0, 0, len(it[1]), len(res)))
            res.extend(it[1])
        elif it[0] == "call":
            _, func, tlist = it
            insts.append((call_op, 1 + len(tlist)))
            typed_arg(func)
            for t in tlist:
                typed_arg(t)
        else:
            insts.append((it[1], 0))
    # Terminador realista (los scripts YSTB terminan en opcode sin args):
    # el key-guess asume que los últimos 4B del code son 12,0,0,0.
    insts.append((0x0C, 0))
    code = b"".join(struct.pack("<BBH", op, argc, 0) for op, argc in insts)
    argblob = b"".join(struct.pack("<HHII", v, t, s, o) for v, t, s, o in args)
    offs = b"\x00" * (4 * len(insts))
    header = b"YSTB" + struct.pack(
        "<7I", 1, len(insts), len(code), len(argblob), len(res), len(offs), 0
    )
    out = bytearray(header + code + argblob + bytes(res) + offs)
    p = 32
    for size in (len(code), len(argblob), len(res), len(offs)):
        _xor_block(out, key, p, size)
        p += size
    return bytes(out)


_SWAP_OLD = bytes(
    [
        0,
        1,
        2,
        72,
        4,
        5,
        53,
        7,
        8,
        11,
        10,
        9,
        16,
        19,
        14,
        15,
        12,
        25,
        18,
        13,
        20,
        27,
        22,
        23,
        24,
        17,
        26,
        21,
        30,
        29,
        28,
        31,
        35,
        33,
        34,
        32,
        36,
        37,
        41,
        39,
        40,
        38,
        42,
        43,
        47,
        45,
        50,
        44,
        48,
        49,
        46,
        51,
        52,
        6,
    ]
    + list(range(54, 256))
)


def _swap_index(length: int) -> int:
    return _SWAP_OLD.index(length)


def build_ypf(files: dict[str, bytes], version: int = 463) -> bytes:
    """files: {nombre: bytes}. Empaqueta estilo YPF v<479 (nombres ^0xFF, zlib)."""
    blobs = {}
    for name, raw in files.items():
        comp = zlib.compress(raw)
        blobs[name] = comp if len(comp) < len(raw) else raw
    names = sorted(files)
    header_size, off = 32, 0
    entries, data = [], bytearray()
    for name in names:
        enc = name.encode("cp932")
        entry_len = 4 + 1 + len(enc) + 1 + 1 + 4 + 4 + 4 + 4
        header_size += entry_len
    for name in names:
        blob = blobs[name]
        raw = files[name]
        entries.append((name, blob, raw, off))
        off += len(blob)
        data.extend(blob)
    out = bytearray()
    out.extend(
        b"YPF\x00"
        + struct.pack("<II", version, len(names))
        + struct.pack("<I", header_size)
        + b"\x00" * 16
    )
    base = header_size
    for name, blob, raw, offset in entries:
        enc = name.encode("cp932")
        out.extend(struct.pack("<I", crc32(enc) & 0xFFFFFFFF))
        out.append(_swap_index(len(enc)) ^ 0xFF)
        out.extend(bytes(b ^ 0xFF for b in enc))
        out.extend(b"\x00")  # type
        out.append(1 if blob != raw else 0)
        out.extend(struct.pack("<II", len(raw), len(blob)))
        out.extend(struct.pack("<I", base + offset))
        out.extend(struct.pack("<I", zlib.adler32(blob) & 0xFFFFFFFF))
    out.extend(data)
    return bytes(out)


DLG_A = [
    ("call", '"es.char.name"', ["直人"]),
    ("msg", "おはよう、{PLAYER}。今日もいい天気だね。"),
    ("msg", "学校へ行こう。"),
    ("call", '"es.sel.set"', ["行く", "休む"]),
    ("other", 0x10),
    ("msg", "これは罠だ。"),
]

DLG_B = [
    ("call", '"es.char.name"', ["美咲"]),
    ("msg", "おはよう、{PLAYER}。今日もいい天気だね。"),  # mismo texto que A (aislamiento)
    ("msg", "別の物語が始まる。"),
]


def make_game(
    root: str,
    name: str,
    scripts: dict[str, list],
    key: int = KEY_A,
    packed: bool = False,
    pac_split: bool = False,
) -> str:
    """Crea un juego sintético. Devuelve el path del juego."""
    gdir = os.path.join(root, name)
    os.makedirs(gdir, exist_ok=True)
    with open(os.path.join(gdir, "yu-ris.exe"), "wb") as f:
        f.write(b"MZ-fake")
    ysbin = os.path.join(gdir, "ysbin")
    os.makedirs(ysbin, exist_ok=True)
    built = {f"ysbin/{fname}": build_ystb(items, key) for fname, items in scripts.items()}
    if packed:
        pac = os.path.join(gdir, "pac")
        os.makedirs(pac, exist_ok=True)
        with open(os.path.join(pac, "ysbin.ypf"), "wb") as f:
            f.write(build_ypf(built))
    if pac_split:
        # Variante real (Natsu no Kusari): sin exe ni sueltos, .ypf solo en pac/.
        import shutil

        shutil.rmtree(ysbin)
        os.remove(os.path.join(gdir, "yu-ris.exe"))
        pac = os.path.join(gdir, "pac")
        os.makedirs(pac, exist_ok=True)
        with open(os.path.join(pac, "bn.ypf"), "wb") as f:
            f.write(build_ypf(built))
    else:
        for arcname, blob in built.items():
            with open(os.path.join(gdir, arcname), "wb") as f:
                f.write(blob)
    return gdir
