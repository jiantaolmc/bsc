#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Compute PancakeSwap Infinity CL PoolId (bytes32) from PoolKey fields.

poolId = keccak256(abi.encode(
    currency0, currency1, hooks, poolManager, fee(uint24), parameters(bytes32)
))

Notes:
- This uses ABI *standard* encoding (32-byte aligned), i.e. abi.encode, NOT abi.encodePacked.
- By default this script sorts currencyA/currencyB into currency0/currency1 by address integer,
  because the PoolManager requires currency0 < currency1.
"""

import argparse
import re

from web_repository.fun.constants import WBNB, BSC_USDT


def keccak256(data: bytes) -> bytes:
    """
    Ethereum Keccak-256 (NOT hashlib.sha3_256).
    Tries pycryptodome first, then eth-hash.
    """
    try:
        from Crypto.Hash import keccak  # pip install pycryptodome
        k = keccak.new(digest_bits=256)
        k.update(data)
        return k.digest()
    except ImportError:
        try:
            from eth_hash.auto import keccak as _keccak  # pip install eth-hash
            return _keccak(data)
        except ImportError:
            raise SystemExit(
                "Missing keccak256 backend.\n"
                "Install one of:\n"
                "  pip install pycryptodome\n"
                "or\n"
                "  pip install eth-hash\n"
            )


def strip_0x(s: str) -> str:
    return s[2:] if s.startswith(("0x", "0X")) else s


def parse_address(addr: str) -> bytes:
    h = strip_0x(addr).lower()
    if not re.fullmatch(r"[0-9a-f]{40}", h):
        raise ValueError(f"Invalid address: {addr}")
    return bytes.fromhex(h)


def abi_encode_address(addr: str) -> bytes:
    # address is 20 bytes, left-padded to 32 bytes
    b = parse_address(addr)
    return b"\x00" * 12 + b


def abi_encode_uint(value: int, bits: int) -> bytes:
    if value < 0 or value >= (1 << bits):
        raise ValueError(f"Value {value} out of range for uint{bits}")
    return value.to_bytes(32, "big")


def abi_encode_bytes32(x: str) -> bytes:
    h = strip_0x(x).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", h):
        raise ValueError(f"Invalid bytes32: {x} (need 64 hex chars)")
    return bytes.fromhex(h)


def compute_pool_id(
    currencyA: str,
    currencyB: str,
    hooks: str,
    poolManager: str,
    fee: int,
    parameters: str,
    sort_currencies: bool = True,
) -> str:
    # sort currencies into (currency0, currency1) by numeric address value
    if sort_currencies:
        a_int = int(parse_address(currencyA).hex(), 16)
        b_int = int(parse_address(currencyB).hex(), 16)
        if a_int <= b_int:
            currency0, currency1 = currencyA, currencyB
        else:
            currency0, currency1 = currencyB, currencyA
    else:
        currency0, currency1 = currencyA, currencyB

    encoded = b"".join(
        [
            abi_encode_address(currency0),
            abi_encode_address(currency1),
            abi_encode_address(hooks),
            abi_encode_address(poolManager),
            abi_encode_uint(fee, 24),         # uint24 -> 32-byte word
            abi_encode_bytes32(parameters),   # bytes32 -> 32-byte word
        ]
    )

    return "0x" + keccak256(encoded).hex()


def main():
    currencyB = BSC_USDT
    currencyA = "0x70f2eadf1ca1969ff42b0c78e9da519e8937cbaf"
    # hooks = "0x9a9B5331ce8d74b2B721291D57DE696E878353fd"
    # hooks = "0x72e09eBd9b24F47730b651889a4eD984CBa53d90"
    hooks = "0xb0baa371b899950b4ef6a27c21baf5ef7c434d0f"
    poolManager = "0xa0ffb9c1ce1fe56963b0321b32e7a0302114058b"
    fee = 67
    parameters = "0x00000000000000000000000000000000000000000000000000000000000A0045"
    # parameters = "0x00000000000000000000000000000000000000000000000000000000000A0055"

    pid = compute_pool_id(
        currencyA=currencyA,
        currencyB=currencyB,
        hooks=hooks,
        poolManager=poolManager,
        fee=fee,
        parameters=parameters,
        sort_currencies=True,  # 默认排序
    )
    print(pid)


if __name__ == "__main__":
    main()