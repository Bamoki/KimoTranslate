"""Lector YPF (YU-RIS): magic YPF\\0, entradas con nombre ofuscado, zlib.

Spec: extYuRis/YpfDef.go. Versiones <479: CRC32-IEEE nombres + adler32 datos;
>=479: murmur2(seed 0). Tablas de longitud y filename-key por versión incluidas.
"""

from __future__ import annotations

import struct
import zlib
from binascii import crc32
from dataclasses import dataclass

MAGIC = b"YPF\x00"

# Tablas de getLengthSwappingTable(version): índice = byte leído ^ 0xFF... no:
# byte_leído = ^b; longitud_real = tabla[^b]. Invertimos: dado índice i, tabla[i].
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
        54,
        55,
        56,
        57,
        58,
        59,
        60,
        61,
        62,
        63,
        64,
        65,
        66,
        67,
        68,
        69,
        70,
        71,
        72,
        73,
        74,
        75,
        76,
        77,
        78,
        79,
        80,
        81,
        82,
        83,
        84,
        85,
        86,
        87,
        88,
        89,
        90,
        91,
        92,
        93,
        94,
        95,
        96,
        97,
        98,
        99,
        100,
        101,
        102,
        103,
        104,
        105,
        106,
        107,
        108,
        109,
        110,
        111,
        112,
        113,
        114,
        115,
        116,
        117,
        118,
        119,
        120,
        121,
        122,
        123,
        124,
        125,
        126,
        127,
        128,
        129,
        130,
        131,
        132,
        133,
        134,
        135,
        136,
        137,
        138,
        139,
        140,
        141,
        142,
        143,
        144,
        145,
        146,
        147,
        148,
        149,
        150,
        151,
        152,
        153,
        154,
        155,
        156,
        157,
        158,
        159,
        160,
        161,
        162,
        163,
        164,
        165,
        166,
        167,
        168,
        169,
        170,
        171,
        172,
        173,
        174,
        175,
        176,
        177,
        178,
        179,
        180,
        181,
        182,
        183,
        184,
        185,
        186,
        187,
        188,
        189,
        190,
        191,
        192,
        193,
        194,
        195,
        196,
        197,
        198,
        199,
        200,
        201,
        202,
        203,
        204,
        205,
        206,
        207,
        208,
        209,
        210,
        211,
        212,
        213,
        214,
        215,
        216,
        217,
        218,
        219,
        220,
        221,
        222,
        223,
        224,
        225,
        226,
        227,
        228,
        229,
        230,
        231,
        232,
        233,
        234,
        235,
        236,
        237,
        238,
        239,
        240,
        241,
        242,
        243,
        244,
        245,
        246,
        247,
        248,
        249,
        250,
        251,
        252,
        253,
        254,
        255,
    ]
)
_SWAP_NEW = bytes(
    [
        0,
        1,
        2,
        10,
        4,
        5,
        53,
        7,
        8,
        11,
        3,
        9,
        16,
        19,
        14,
        15,
        12,
        24,
        18,
        13,
        46,
        27,
        22,
        23,
        17,
        25,
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
        20,
        44,
        48,
        49,
        50,
        51,
        52,
        6,
        54,
        55,
        56,
        57,
        58,
        59,
        60,
        61,
        62,
        63,
        64,
        65,
        66,
        67,
        68,
        69,
        70,
        71,
        72,
        73,
        74,
        75,
        76,
        77,
        78,
        79,
        80,
        81,
        82,
        83,
        84,
        85,
        86,
        87,
        88,
        89,
        90,
        91,
        92,
        93,
        94,
        95,
        96,
        97,
        98,
        99,
        100,
        101,
        102,
        103,
        104,
        105,
        106,
        107,
        108,
        109,
        110,
        111,
        112,
        113,
        114,
        115,
        116,
        117,
        118,
        119,
        120,
        121,
        122,
        123,
        124,
        125,
        126,
        127,
        128,
        129,
        130,
        131,
        132,
        133,
        134,
        135,
        136,
        137,
        138,
        139,
        140,
        141,
        142,
        143,
        144,
        145,
        146,
        147,
        148,
        149,
        150,
        151,
        152,
        153,
        154,
        155,
        156,
        157,
        158,
        159,
        160,
        161,
        162,
        163,
        164,
        165,
        166,
        167,
        168,
        169,
        170,
        171,
        172,
        173,
        174,
        175,
        176,
        177,
        178,
        179,
        180,
        181,
        182,
        183,
        184,
        185,
        186,
        187,
        188,
        189,
        190,
        191,
        192,
        193,
        194,
        195,
        196,
        197,
        198,
        199,
        200,
        201,
        202,
        203,
        204,
        205,
        206,
        207,
        208,
        209,
        210,
        211,
        212,
        213,
        214,
        215,
        216,
        217,
        218,
        219,
        220,
        221,
        222,
        223,
        224,
        225,
        226,
        227,
        228,
        229,
        230,
        231,
        232,
        233,
        234,
        235,
        236,
        237,
        238,
        239,
        240,
        241,
        242,
        243,
        244,
        245,
        246,
        247,
        248,
        249,
        250,
        251,
        252,
        253,
        254,
        255,
    ]
)


def _murmur2(data: bytes, seed: int = 0) -> int:
    """MurmurHash2 x86 32-bit (go-murmur). Solo para checksum YPF v>=479."""
    m, r = 0x5BD1E995, 24
    h = (seed ^ len(data)) & 0xFFFFFFFF
    n = len(data) - len(data) % 4
    for i in range(0, n, 4):
        k = struct.unpack_from("<I", data, i)[0]
        k = (k * m) & 0xFFFFFFFF
        k ^= k >> r
        k = (k * m) & 0xFFFFFFFF
        h = (h * m) & 0xFFFFFFFF
        h ^= k
    tail = data[n:]
    if len(tail) >= 3:
        h ^= tail[2] << 16
    if len(tail) >= 2:
        h ^= tail[1] << 8
    if len(tail) >= 1:
        h ^= tail[0]
        h = (h * m) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * m) & 0xFFFFFFFF
    return (h ^ (h >> 15)) & 0xFFFFFFFF


def _name_key(version: int) -> int:
    if version == 290:
        return 64
    if version > 500:
        return 54
    return 0


def _swap(version: int) -> bytes:
    return _SWAP_NEW if version >= 500 else _SWAP_OLD


@dataclass
class YpfEntry:
    name: str
    type: int
    is_compressed: bool
    raw_size: int
    packed_size: int
    offset: int
    data_checksum: int
    name_checksum: int


class YpfError(Exception):
    pass


def parse_ypf(data: bytes) -> tuple[int, list[YpfEntry]]:
    """Devuelve (version, entradas). Verifica checksums de nombre."""
    if data[:4] != MAGIC:
        raise YpfError("not a YPF archive")
    version, file_count = struct.unpack_from("<II", data, 4)
    swap, nkey = _swap(version), _name_key(version)
    pos, entries = 32, []
    for _ in range(file_count):
        name_sum = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        raw_len = swap[data[pos] ^ 0xFF]
        pos += 1
        enc = data[pos : pos + raw_len]
        pos += raw_len
        dec_name = bytes((b ^ 0xFF) ^ nkey for b in enc)
        name = dec_name.decode("cp932")
        if version < 479:
            expect = crc32(dec_name) & 0xFFFFFFFF
        else:
            expect = _murmur2(dec_name)
        if expect != name_sum:
            raise YpfError(f"name checksum failed for {name!r}")
        ftype, comp, raw_sz, packed_sz = struct.unpack_from("<BBII", data, pos)
        pos += 10
        if version < 479:
            (off,) = struct.unpack_from("<I", data, pos)
            pos += 4
        else:
            (off,) = struct.unpack_from("<Q", data, pos)
            pos += 8
        (data_sum,) = struct.unpack_from("<I", data, pos)
        pos += 4
        entries.append(YpfEntry(name, ftype, comp == 1, raw_sz, packed_sz, off, data_sum, name_sum))
    entries.sort(key=lambda e: e.offset)
    return version, entries


def extract_entry(data: bytes, entry: YpfEntry, version: int) -> bytes:
    blob = data[entry.offset : entry.offset + entry.packed_size]
    if version < 479:
        expect = zlib.adler32(blob) & 0xFFFFFFFF
    else:
        expect = _murmur2(blob)
    if expect != entry.data_checksum:
        raise YpfError(f"data checksum failed for {entry.name!r}")
    if not entry.is_compressed:
        return blob
    out = zlib.decompressobj().decompress(blob)
    if len(out) != entry.raw_size:
        raise YpfError(f"size mismatch for {entry.name!r}")
    return out
