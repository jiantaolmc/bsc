# -*- coding: utf-8 -*-
import os
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

from web3 import Web3


getcontext().prec = 80

# =========================
# 你只需要改这里
# =========================
BSC_RPC = os.getenv("BSC_RPC", "https://bsc-dataseed.binance.org/")
w3 = Web3(Web3.HTTPProvider(BSC_RPC, request_kwargs={"timeout": 25}))

TXS = [
    "0x5c4fcae834864b14f42cbb18e83fd87869b1b52f82052dceefeade68d1df12f3",
    "0xc506f434087e209529b862af131b49f8e160c29e5856d6efc99d892e088c4e18",
]


# 可选：想把 BNB 区间也换算成 USD（近似），填当时 BNB_USD
BNB_USD: Optional[Decimal] = None
# BNB_USD = Decimal("900")


# WBNB / USDT（BSC）
WBNB = Web3.to_checksum_address("0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c")
USDT = Web3.to_checksum_address("0x55d398326f99059fF775485246999027B3197955")

# PancakeSwap V2 Router (BSC)
PCS_V2_ROUTER = Web3.to_checksum_address("0x10ED43C718714eb63d5aA57B78B54704E256024E")
PCS_V2_ABI = [{
    "name": "getAmountsOut",
    "type": "function",
    "stateMutability": "view",
    "inputs": [
        {"name": "amountIn", "type": "uint256"},
        {"name": "path", "type": "address[]"}
    ],
    "outputs": [{"name": "amounts", "type": "uint256[]"}],
}]


def get_bnb_usdt_price(w3: Web3) -> Decimal:
    """
    返回 1 BNB = ? USDT（用 WBNB->USDT 的 v2 报价近似）
    """
    router = w3.eth.contract(address=PCS_V2_ROUTER, abi=PCS_V2_ABI)
    amounts = router.functions.getAmountsOut(10**18, [WBNB, USDT]).call()
    # USDT 18 decimals on BSC? 实际 USDT 是 18（BSC-USDT 是 18）
    return Decimal(amounts[-1]) / Decimal(10**18)


# =========================
# 已知地址（你也可以自己加）
# =========================
INF_CL_PM = Web3.to_checksum_address("0x55f4c8abA71A1e923edC303eb4fEfF14608cC226")  # Infinity CLPositionManager
V3_NPM   = Web3.to_checksum_address("0x46A15B0b27311cedF172AB29E4f4766fbE7F4364")     # Pancake v3 NPM（可选）

NATIVE = "0x0000000000000000000000000000000000000000"
MAX_UINT128 = (1 << 128) - 1  # 关键修复点：过滤这个哨兵值

STABLES = {
    Web3.to_checksum_address("0x55d398326f99059fF775485246999027B3197955"): "USDT",
    Web3.to_checksum_address("0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"): "USDC",
    Web3.to_checksum_address("0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56"): "BUSD",
}

ERC20_ABI_MIN = [
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
]

# ERC20 / ERC721 Transfer topic（签名相同）
TRANSFER_TOPIC0 = Web3.keccak(text="Transfer(address,address,uint256)").hex()


def ck(addr: str) -> str:
    if addr.lower() == NATIVE:
        return NATIVE
    return Web3.to_checksum_address(addr)


def selector(sig: str) -> bytes:
    return Web3.keccak(text=sig)[:4]


def tick_to_price_token1_per_token0(tick: int, dec0: int, dec1: int) -> Decimal:
    base = Decimal("1.0001")
    return (base ** Decimal(tick)) * (Decimal(10) ** Decimal(dec0 - dec1))


def fmt_price(x: Decimal) -> str:
    ax = abs(x)
    if ax >= Decimal("1000"):
        return f"{x:.4f}"
    if ax >= Decimal("1"):
        return f"{x:.6f}"
    if ax >= Decimal("0.01"):
        return f"{x:.6f}"
    return f"{x:.9f}"


def fmt_human(x: Decimal) -> str:
    ax = abs(x)
    if ax >= Decimal(1_000_000):
        return f"{(x/Decimal(1_000_000)):.0f}M"
    if ax >= Decimal(1_000):
        return f"{(x/Decimal(1_000)):.0f}K"
    if ax >= Decimal(1):
        if x == x.to_integral_value():
            return f"{int(x)}"
        return f"{x:.4f}"
    return f"{x:.6f}"


def print_centered_table(headers: List[str], rows: List[List[str]], width: int = 140):
    col_w = []
    for i, h in enumerate(headers):
        mx = len(h)
        for r in rows:
            mx = max(mx, len(r[i]))
        col_w.append(mx)

    table_w = sum(col_w) + (len(col_w) - 1) * 3
    left_pad = max(0, (width - table_w) // 2)

    def line(parts: List[str]) -> str:
        return (" " * left_pad) + "   ".join(parts)

    header_parts = [headers[i].ljust(col_w[i]) for i in range(len(headers))]
    sep_parts = ["-" * col_w[i] for i in range(len(headers))]

    print(line(header_parts))
    print(line(sep_parts))
    for r in rows:
        parts = [r[i].ljust(col_w[i]) for i in range(len(headers))]
        print(line(parts))


def get_token_meta(w3: Web3, addr: str, cache: Dict[str, Tuple[str, int]]) -> Tuple[str, int]:
    addr = ck(addr)
    if addr == NATIVE:
        return ("BNB", 18)
    if addr in cache:
        return cache[addr]
    c = w3.eth.contract(address=addr, abi=ERC20_ABI_MIN)
    sym = c.functions.symbol().call()
    dec = int(c.functions.decimals().call())
    cache[addr] = (sym, dec)
    return sym, dec


def topic_to_addr(topic) -> str:
    h = topic.hex()
    if h.startswith("0x"):
        h = h[2:]
    return Web3.to_checksum_address("0x" + h[-40:])


def sum_erc20_outflow_from_user(receipt_logs: List[Dict[str, Any]], token_addr: str, user_addr: str) -> int:
    """
    统计该 tx 中：token 的 Transfer(from=user_addr, value=...) 的总和
    """
    token_addr = ck(token_addr)
    if token_addr == NATIVE:
        return 0

    user_addr = Web3.to_checksum_address(user_addr)
    total = 0

    for lg in receipt_logs:
        if Web3.to_checksum_address(lg["address"]) != token_addr:
            continue
        topics = lg["topics"]
        # ERC20 Transfer: topics = [topic0, from, to] (len=3)
        if not topics or len(topics) != 3:
            continue
        if topics[0].hex() != TRANSFER_TOPIC0:
            continue
        from_addr = topic_to_addr(topics[1])
        if from_addr != user_addr:
            continue
        val = int.from_bytes(lg["data"], byteorder="big")
        total += val

    return total


def parse_minted_token_ids_from_receipt(receipt: Any, pm_addr: str) -> List[int]:
    """从 receipt.logs 里找 ERC721 mint 的 tokenId（Transfer from 0x0）"""
    pm_addr = Web3.to_checksum_address(pm_addr)
    out = []
    for lg in receipt["logs"]:
        if Web3.to_checksum_address(lg["address"]) != pm_addr:
            continue
        topics = lg["topics"]
        # ERC721 Transfer: topics = [topic0, from, to, tokenId] (len=4)
        if not topics or len(topics) != 4:
            continue
        if topics[0].hex() != TRANSFER_TOPIC0:
            continue
        from_addr = topic_to_addr(topics[1])
        if int(from_addr, 16) != 0:
            continue
        token_id = int(topics[3].hex(), 16)
        out.append(token_id)
    return out


# -------------------------
# Infinity (v4) 解 calldata
# -------------------------
def extract_infinity_action_plans(w3: Web3, calldata: bytes) -> List[Tuple[bytes, List[bytes]]]:
    """
    返回若干个 (actions_bytes, params_bytes_list)
    兼容：modifyLiquidities(payload, deadline) / multicall 包裹
    """
    plans: List[Tuple[bytes, List[bytes]]] = []

    SIG_MODIFY = "modifyLiquidities(bytes,uint256)"
    SIG_MULTI_1 = "multicall(bytes[])"
    SIG_MULTI_2 = "multicall(uint256,bytes[])"

    sel_modify = selector(SIG_MODIFY)
    sel_multi_1 = selector(SIG_MULTI_1)
    sel_multi_2 = selector(SIG_MULTI_2)

    stack = [calldata]
    while stack:
        data = stack.pop()
        if len(data) < 4:
            continue
        mid = data[:4]

        if mid == sel_modify:
            payload, _deadline = w3.codec.decode(["bytes", "uint256"], data[4:])
            actions, params = w3.codec.decode(["bytes", "bytes[]"], payload)
            plans.append((actions, list(params)))
            continue

        if mid == sel_multi_1:
            (calls,) = w3.codec.decode(["bytes[]"], data[4:])
            for c in calls:
                stack.append(c)
            continue

        if mid == sel_multi_2:
            _deadline, calls = w3.codec.decode(["uint256", "bytes[]"], data[4:])
            for c in calls:
                stack.append(c)
            continue

    return plans


def decode_cl_mint_position_param(w3: Web3, param: bytes) -> Tuple[Tuple[Any, ...], int, int, int, int]:
    """
    解 CL_MINT_POSITION 的 params：
      (PoolKey, tickLower, tickUpper, liquidity, amount0Max, amount1Max, owner, hookData)

    PoolKey struct：
      (currency0, currency1, hooks, poolManager, fee(uint24), parameters(bytes32))
    """
    decoded = w3.codec.decode(
        [
            "(address,address,address,address,uint24,bytes32)",
            "int24",
            "int24",
            "uint256",
            "uint128",
            "uint128",
            "address",
            "bytes",
        ],
        param,
    )
    pool_key = decoded[0]
    tick_lower = int(decoded[1])
    tick_upper = int(decoded[2])
    amount0_max = int(decoded[4])
    amount1_max = int(decoded[5])
    return pool_key, tick_lower, tick_upper, amount0_max, amount1_max


def classify_nature(base_amt: Decimal, token_amt: Decimal) -> str:
    # 这里 base_amt = 稳定币或BNB；token_amt = 另一侧Token
    if base_amt > 0 and token_amt > 0:
        return "🟡 双边做市"
    if base_amt > 0 and token_amt == 0:
        return "🟢 买入支撑"
    if base_amt == 0 and token_amt > 0:
        return "🔴 卖出区"
    return "?"


def main():
    if not w3.is_connected():
        raise SystemExit(f"RPC 连接失败: {BSC_RPC}")

    token_cache: Dict[str, Tuple[str, int]] = {}
    rows: List[List[str]] = []

    for txh in TXS:
        txh = txh.strip()
        if not txh:
            continue
        if not txh.startswith("0x"):
            txh = "0x" + txh

        tx = w3.eth.get_transaction(txh)
        receipt = w3.eth.get_transaction_receipt(txh)

        to_addr = tx.get("to")
        if to_addr is None:
            continue
        to_addr = Web3.to_checksum_address(to_addr)
        calldata = bytes.fromhex(tx["input"].hex()[2:])
        tx_from = Web3.to_checksum_address(tx["from"])

        # ========== Infinity CLPositionManager ==========
        if to_addr == INF_CL_PM:
            minted_ids = parse_minted_token_ids_from_receipt(receipt, INF_CL_PM)
            plans = extract_infinity_action_plans(w3, calldata)

            # action==0x02 认为是 CL_MINT_POSITION
            mints = []
            for actions, params in plans:
                if len(actions) != len(params):
                    continue
                for act, p in zip(actions, params):
                    if act == 0x02:
                        pool_key, tick_lower, tick_upper, a0max, a1max = decode_cl_mint_position_param(w3, p)
                        mints.append((pool_key, tick_lower, tick_upper, a0max, a1max))

            for i, (pool_key, tick_lower, tick_upper, a0max, a1max) in enumerate(mints):
                token_id = minted_ids[i] if i < len(minted_ids) else -1

                currency0 = ck(pool_key[0])
                currency1 = ck(pool_key[1])

                sym0, dec0 = get_token_meta(w3, currency0, token_cache)
                sym1, dec1 = get_token_meta(w3, currency1, token_cache)

                # 关键修复点 1：MAX_UINT128 不是实际数量，先忽略
                a0max_eff = 0 if a0max == MAX_UINT128 else a0max
                a1max_eff = 0 if a1max == MAX_UINT128 else a1max

                # 关键修复点 2：优先用 Transfer(from=tx.from) 统计实际转出
                out0_raw = tx["value"] if currency0 == NATIVE else sum_erc20_outflow_from_user(receipt["logs"], currency0, tx_from)
                out1_raw = tx["value"] if currency1 == NATIVE else sum_erc20_outflow_from_user(receipt["logs"], currency1, tx_from)

                # 如果没统计到（=0），回退用 amountMax（但过滤掉 MAX_UINT128）
                if out0_raw == 0 and a0max_eff != 0:
                    out0_raw = a0max_eff
                if out1_raw == 0 and a1max_eff != 0:
                    out1_raw = a1max_eff

                amt0 = Decimal(out0_raw) / (Decimal(10) ** dec0)
                amt1 = Decimal(out1_raw) / (Decimal(10) ** dec1)

                # tick -> price(token1/token0)
                pL = tick_to_price_token1_per_token0(tick_lower, dec0, dec1)
                pU = tick_to_price_token1_per_token0(tick_upper, dec0, dec1)

                # 识别 stable / BNB
                stable_side = None
                if currency0 != NATIVE and currency0 in STABLES:
                    stable_side = 0
                elif currency1 != NATIVE and currency1 in STABLES:
                    stable_side = 1

                has_bnb = (currency0 == NATIVE) or (currency1 == NATIVE)

                if stable_side is not None:
                    if stable_side == 1:
                        # token0=Token, token1=Stable => USD/Token0 = p
                        usd_low, usd_up = pL, pU
                        base_amt = amt1
                        token_amt = amt0
                        token_symbol = sym0
                    else:
                        # token0=Stable, token1=Token => USD/Token1 = 1/p
                        usd_low = (Decimal(1) / pU) if pU != 0 else Decimal(0)
                        usd_up  = (Decimal(1) / pL) if pL != 0 else Decimal(0)
                        base_amt = amt0
                        token_amt = amt1
                        token_symbol = sym1

                    price_range = f"${fmt_price(usd_low)} → ${fmt_price(usd_up)}"
                    base_str = fmt_human(base_amt)
                    token_str = fmt_human(token_amt)
                    nature = classify_nature(base_amt, token_amt)

                    rows.append([
                        f"#{token_id}" if token_id >= 0 else "#?",
                        price_range,
                        base_str,
                        f"{token_str}",
                        nature
                    ])

                elif has_bnb:
                    # BNB 区间
                    if currency1 == NATIVE:
                        # token0=Token, token1=BNB => BNB/Token0 = p
                        bnb_low, bnb_up = pL, pU
                        base_amt = amt1
                        token_amt = amt0
                        token_symbol = sym0
                    else:
                        # token0=BNB, token1=Token => BNB/Token1 = 1/p
                        bnb_low = (Decimal(1) / pU) if pU != 0 else Decimal(0)
                        bnb_up  = (Decimal(1) / pL) if pL != 0 else Decimal(0)
                        base_amt = amt0
                        token_amt = amt1
                        token_symbol = sym1

                    if BNB_USD is not None and BNB_USD > 0:
                        usd_low = bnb_low * BNB_USD
                        usd_up  = bnb_up  * BNB_USD
                        price_range = f"${fmt_price(usd_low)} → ${fmt_price(usd_up)}"
                    else:
                        price_range = f"{fmt_price(bnb_low)} BNB → {fmt_price(bnb_up)} BNB"

                    base_str = f"{fmt_human(base_amt)}"
                    token_str = f"{fmt_human(token_amt)}"
                    nature = classify_nature(base_amt, token_amt)

                    rows.append([
                        f"#{token_id}" if token_id >= 0 else "#?",
                        price_range,
                        base_str,
                        token_str,
                        nature
                    ])

            continue

        # 其它 to 地址这版先不解析（你要我再加 router/别的 manager 再说）
        continue

    if not rows:
        print("没有解析出任何 CL_MINT_POSITION。")
        return

    headers = ["Position ID", "价格区间", "USDT/BNB 数量", "Token 数量", "性质"]
    print()
    print_centered_table(headers, rows, width=140)
    print()


if __name__ == "__main__":
    try:
        BNB_USD = get_bnb_usdt_price(w3)  # 方案A：链上取
    except Exception:
        BNB_USD = None
    main()
