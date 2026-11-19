"""Fiat–Shamir OR proofs of bit commitments over libsodium Ristretto255."""
import ctypes as c
from ctypes.util import find_library
from hashlib import sha512
from pathlib import Path
import sys
from secrets import randbelow

if sys.platform == "win32":
    sodium = c.CDLL(str(Path(__file__).resolve().with_name("libsodium.dll")))
else:
    sodium = c.CDLL(find_library("sodium") or "libsodium.so.23")
if sodium.sodium_init() < 0:
    raise RuntimeError("libsodium initialization failed")

ORDER = 2**252 + 27742317777372353535851937790883648493
ZERO = bytes(32)
BITS = 32
MAX = 2**BITS - 1


def encode(x):
    return (x % ORDER).to_bytes(32, "little")


def output(name, *parts):
    buffer = c.create_string_buffer(32)
    result = getattr(sodium, name)(buffer, *parts)
    if result != 0:
        raise ValueError("Invalid Ristretto operation")
    return buffer.raw


def point(raw):
    if len(raw) != 32 or sodium.crypto_core_ristretto255_is_valid_point(raw) != 1:
        raise ValueError("Invalid Ristretto point")
    return raw


def scalar(raw):
    if len(raw) != 32 or int.from_bytes(raw, "little") >= ORDER:
        raise ValueError("Invalid Ristretto scalar")
    return int.from_bytes(raw, "little")


def add(a, b):
    return output("crypto_core_ristretto255_add", a, b)


def sub(a, b):
    return output("crypto_core_ristretto255_sub", a, b)


def mul(k, base):
    if k % ORDER == 0 or base == ZERO:
        return ZERO
    return output("crypto_scalarmult_ristretto255", encode(k), base)


G = output("crypto_scalarmult_ristretto255_base", encode(1))
H = output("crypto_core_ristretto255_from_hash", sha512(b"LegitZK/APBD/v1/blinding-generator").digest())


def commit(amount, blind):
    return add(mul(amount, G), mul(blind, H))


def challenge(context, index, side, C, A0, A1):
    transcript = b"LegitZK/APBD/v1/bit-or\x00" + context + bytes([side, index]) + C + A0 + A1
    return int.from_bytes(sha512(transcript).digest(), "little") % ORDER


def prove_bits(value, blind, context, side):
    if not 0 <= value <= MAX:
        raise ValueError("Private predicate is false")
    proof = []
    unused_blind = blind
    for i in range(BITS):
        bit = (value >> i) & 1
        weight = 1 << i
        r = randbelow(ORDER) if i < BITS - 1 else unused_blind * pow(weight, -1, ORDER) % ORDER
        unused_blind = (unused_blind - weight * r) % ORDER
        C = commit(bit, r)
        statements = [C, sub(C, G)]
        fake = 1 - bit
        e, z, A = [0, 0], [0, 0], [None, None]
        e[fake], z[fake], nonce = (randbelow(ORDER) for _ in range(3))
        A[fake] = sub(mul(z[fake], H), mul(e[fake], statements[fake]))
        A[bit] = mul(nonce, H)
        e[bit] = (challenge(context, i, side, C, *A) - e[fake]) % ORDER
        z[bit] = (nonce + e[bit] * r) % ORDER
        proof.append((C + encode(e[0]) + encode(z[0]) + encode(e[1]) + encode(z[1])).hex())
    return proof


def verify_bits(proof, expected, context, side):
    if len(proof) != BITS:
        return False
    aggregate = ZERO
    for i, item in enumerate(proof):
        if not isinstance(item, str) or len(item) != 320:
            return False
        raw = bytes.fromhex(item)
        C = point(raw[:32])
        e0, z0, e1, z1 = (scalar(raw[j:j + 32]) for j in range(32, 160, 32))
        A0 = sub(mul(z0, H), mul(e0, C))
        A1 = sub(mul(z1, H), mul(e1, sub(C, G)))
        if (e0 + e1) % ORDER != challenge(context, i, side, C, A0, A1):
            return False
        aggregate = add(aggregate, mul(1 << i, C))
    return aggregate == expected


def prove(amount, blind, threshold, context):
    return [prove_bits(amount - threshold, blind, context, 0),
            prove_bits(MAX - amount, -blind, context, 1)]


def verify(proof, commitment, threshold, context):
    return (isinstance(proof, list) and len(proof) == 2
            and verify_bits(proof[0], sub(commitment, mul(threshold, G)), context, 0)
            and verify_bits(proof[1], sub(mul(MAX, G), commitment), context, 1))
