"""Parser YSTB (YU-RIS compiled script). Spec: extYuRis/YstbDef.go.

Header 32B: YSTB + version u32 + inst_cnt/code/arg/res/off/resv u32.
Secciones XOR 4-byte por separado. Args: Type 3 = string con {type u8,len u16};
Type!=0 raw con ResInfo; Type 0 multi-arg = solo offsets.
Texto: opcode msg (1 arg japonés) + opcode call ("es.*") con funciones de texto.
Repack: strings nuevas al tail de recursos + parcheo de offsets (cualquier longitud).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

MAGIC = b"YSTB"
HEADER_SIZE = 32
DEFAULT_KEYS = (0x96AC6FD3, 0x6CFDDADB, 0x30731B78)

# Funciones call cuyos args type-3 son traducibles (extYuRis).
TEXT_FUNCS = {
    '"es.sel.set"',
    '"es.char.name.mark.set"',
    '"es.char.name"',
    '"es.input.str.set"',
    '"es.tips.def.set"',
    '"es.tips.tx.def.set"',
}

NAME_FUNCS = {'"es.char.name.mark.set"', '"es.char.name"'}  # fijan speaker
CHOICE_FUNCS = {'"es.sel.set"'}  # args = opciones


class YstbError(Exception):
    pass


def _xor(data: bytearray, key: bytes, start: int, size: int) -> None:
    for i in range(size):
        data[start + i] ^= key[i & 3]


def _key_bytes(key: int) -> bytes:
    return struct.pack("<I", key)


def guess_key(data: bytes) -> int:
    """Últimos 4B de la sección code son un offset que en claro vale 12,0,0,0."""
    inst_cnt, code_size = struct.unpack_from("<II", data, 8)
    if code_size != inst_cnt * 4 or len(data) < HEADER_SIZE + code_size:
        raise YstbError("bad header for key guess")
    at = HEADER_SIZE + code_size - 4
    cipher = data[at : at + 4]
    plain = bytes([12, 0, 0, 0])
    return struct.unpack("<I", bytes(c ^ p for c, p in zip(cipher, plain, strict=True)))[0]


def decrypt(data: bytes, key: int) -> bytearray:
    if data[:4] != MAGIC:
        raise YstbError("not YSTB")
    inst_cnt, code_size, arg_size, res_size, off_size = struct.unpack_from("<5I", data, 8)
    if code_size != inst_cnt * 4:
        raise YstbError("code/inst mismatch")
    if HEADER_SIZE + code_size + arg_size + res_size + off_size != len(data):
        raise YstbError("size mismatch")
    out, kb, p = bytearray(data), _key_bytes(key), HEADER_SIZE
    for size in (code_size, arg_size, res_size, off_size):
        _xor(out, kb, p, size)
        p += size
    return out


@dataclass
class Arg:
    value: int
    type: int
    data: bytes = b""  # recurso decodificado (raw o typed)
    res_type: int = 0
    res_offset: int = 0
    res_size: int = 0


@dataclass
class Inst:
    op: int
    label: int
    args: list = field(default_factory=list)


@dataclass
class Script:
    insts: list  # Inst
    res_start: int
    header: bytes  # 32B originales (para repack)
    raw: bytearray  # todo descifrado (para repack)


def parse(data: bytes, key: int) -> Script:
    try:
        return _parse_inner(data, key)
    except (struct.error, IndexError, ValueError) as e:
        raise YstbError(f"parse failed (wrong key or corrupt file): {e}") from e


def _parse_inner(data: bytes, key: int) -> Script:
    dec = decrypt(data, key)
    inst_cnt, code_size, arg_size = struct.unpack_from("<3I", dec, 8)
    raw_insts = [struct.unpack_from("<BBH", dec, HEADER_SIZE + i * 4) for i in range(inst_cnt)]
    nargs = arg_size // 12
    raw_args = [
        struct.unpack_from("<HHII", dec, HEADER_SIZE + code_size + i * 12) for i in range(nargs)
    ]
    res_start = HEADER_SIZE + code_size + arg_size
    insts, ai = [], 0
    for op, argc, label in raw_insts:
        inst = Inst(op, label, [])
        for _ in range(argc):
            value, typ, size, off = raw_args[ai]
            ai += 1
            arg = Arg(value, typ, res_offset=off, res_size=size)
            if typ != 0 or argc == 1:
                arg.data, arg.res_type = _read_res(dec, res_start, typ, size, off)
            inst.args.append(arg)
        insts.append(inst)
    return Script(insts, res_start, bytes(data[:HEADER_SIZE]), dec)


def _read_res(dec: bytearray, res_start: int, typ: int, size: int, off: int) -> tuple[bytes, int]:
    base = res_start + off
    if typ == 3:
        rtype, length = struct.unpack_from("<BH", dec, base)
        return bytes(dec[base + 3 : base + 3 + length]), rtype
    if size > 3:
        rtype, length = struct.unpack_from("<BH", dec, base)
        if length + 3 == size:
            return bytes(dec[base + 3 : base + 3 + length]), rtype
    return bytes(dec[base : base + size]), 0


def decode(data: bytes) -> str | None:
    try:
        return data.decode("cp932")
    except (UnicodeDecodeError, ValueError):
        return None


def is_jp(data: bytes) -> bool:
    return bool(data) and data[0] > 0x80 and decode(data) is not None


def guess_ops(script: Script, msg_op: int = -1, call_op: int = -1) -> tuple[int, int]:
    """msg: el op con args únicos japoneses (densidad 1.0 vale desde 1;
    si hay ruido, >=3 y >=80%). call: >=1 firma "es...*"."""
    from collections import Counter

    msgs, single, calls = Counter(), Counter(), Counter()
    for inst in script.insts:
        if len(inst.args) == 1:
            single[inst.op] += 1
            if is_jp(inst.args[0].data):
                msgs[inst.op] += 1
        if (
            inst.args
            and inst.args[0].type == 3
            and (s := decode(inst.args[0].data) or "").startswith('"es')
            and s.endswith('"')
            and len(s) > 4
        ):
            calls[inst.op] += 1
    if msg_op < 0:
        cands = [
            (n, op)
            for op, n in msgs.items()
            if (n >= 3 and n / single[op] >= 0.8) or n == single[op]
        ]
        msg_op = max(cands)[1] if cands else -1
    if call_op < 0:
        call_op = max(calls.items(), key=lambda kv: kv[1])[0] if calls else -1
    return msg_op, call_op


def repack(script: Script, texts: list[str], msg_op: int, call_op: int, key: int) -> bytes:
    """Nuevos strings al tail de recursos + parcheo de offsets. Cualquier longitud."""
    inst_cnt, code_size, arg_size, res_size, off_size = struct.unpack_from("<5I", script.header, 8)
    args_off = HEADER_SIZE + code_size
    args = bytearray(script.raw[args_off : args_off + arg_size])
    tail, new_off, ti, ai = bytearray(), res_size, 0, 0

    def put(arg: Arg, text: str) -> None:
        nonlocal ti, new_off
        raw = text.encode("cp932")
        blob = struct.pack("<BH", arg.res_type, len(raw)) + raw if arg.type == 3 else raw
        tail.extend(blob)
        struct.pack_into("<II", args, ai * 12 + 4, len(blob), new_off)
        new_off += len(blob)
        ti += 1

    for inst in script.insts:
        fname = decode(inst.args[0].data) or "" if inst.args else ""
        for j, arg in enumerate(inst.args):
            if inst.op == msg_op and j == 0 and len(inst.args) == 1:
                put(arg, texts[ti])
            elif (
                inst.op == call_op
                and j > 0
                and arg.type == 3
                and fname in TEXT_FUNCS
                and arg.data not in (b'""', b"''")
            ):
                put(arg, texts[ti])
            ai += 1
    if ti != len(texts):
        raise YstbError(f"texts mismatch: {len(texts)} given, {ti} slots")
    hdr = bytearray(script.header)
    struct.pack_into("<I", hdr, 20, res_size + len(tail))  # ResourceSize
    out = bytes(hdr) + bytes(script.raw[HEADER_SIZE:args_off]) + bytes(args)
    out += bytes(script.raw[args_off + arg_size : args_off + arg_size + res_size]) + bytes(tail)
    out += bytes(script.raw[args_off + arg_size + res_size :])
    kb, enc, p = _key_bytes(key), bytearray(out), HEADER_SIZE
    for size in (code_size, arg_size, res_size + len(tail), off_size):
        _xor(enc, kb, p, size)
        p += size
    return bytes(enc)
