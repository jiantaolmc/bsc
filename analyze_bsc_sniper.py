from __future__ import annotations

"""
CLMM exact-in quote helper for Uniswap v3 / Pancake v3 / Pancake Infinity style
concentrated-liquidity pools (when there is no extra hook delta or token tax).

What this script does
---------------------
Given:
- fee_pips
- current sqrtPriceX96
- current tick
- pool token decimals
- each LP position's tick range + (liquidity OR mint-time amounts)
- one or more exact-input trade sizes
- optional BNB_PRICE (USD) for BNB/WBNB pairs

It estimates:
- how many tokens you receive
- average execution price
- post-trade spot price ("price after your buy")
- optional USD equivalents for those prices

Important
---------
1) To quote a *freshly created* pool from mint tx logs, you can use position
   amount0/amount1 from the mint/add events.
2) To quote a *live pool after trades happened*, do NOT rely on the old
   amount0/amount1. In that case you should input each position's `liquidity`
   instead (from on-chain events / state), plus the latest sqrtPriceX96/tick.
3) This script only includes the pool fee (`fee_pips`).
   If the pool has hook fee, protocol fee, router fee, or token tax, real output
   will be lower.

Fee units
---------
Pancake / Uniswap style fee pips in this script use 1e-6 units:
- 67   => 0.0067%
- 500  => 0.05%
- 2500 => 0.25%
- 3000 => 0.30%
- 10000 => 1.00%
"""

from decimal import Decimal, getcontext
import math
from typing import Dict, List, Tuple, Any, Optional

getcontext().prec = 90
Q96 = Decimal(2) ** 96
DEFAULT_STABLE_SYMBOLS = {"USDT", "USDC", "BUSD", "FDUSD", "DAI", "USDD", "TUSD", "USDP"}
DEFAULT_BNB_SYMBOLS = {"BNB", "WBNB"}


# =========================
# Editable config starts here
# =========================
CONFIG: Dict[str, Any] = {
    # Token metadata
    "token0_symbol": "USDT",   # quote asset in the example pool
    "token1_symbol": "EDGE",    # target token in the example pool
    "decimals0": 18,
    "decimals1": 18,

    # Optional USD conversion
    # If one side is BNB / WBNB, set BNB_PRICE so avg price and post-trade spot
    # can also be shown in USD ("U").
    # Example: if BNB_PRICE = 600, then 0.00005 BNB/UP = 0.03 USD/UP.
    "BNB_PRICE": "651",

    # Optional per-symbol USD overrides. Only needed if you want a direct USD
    # mapping for symbols that are NOT stablecoins and NOT BNB/WBNB.
    # Example: {"ETH": "3500"}
    "symbol_usd_price": {},

    # Current pool state
    "fee_pips": 67,
    "sqrt_price_x96": 112045541949572279837463876454,
    "current_tick": 6931,

    # LP positions currently in the pool.
    # Preferred for fresh pools: amount0 + amount1 from the add/mint tx.
    # Preferred for live pools after trades: liquidity + tick range.
    "positions": [
        {
            "name": "LP1",
            "tick_lower": 0,
            "tick_upper": 13860,
            "amount0": "350000",
            "amount1": "700307",
            # Optional alternative:
            # "liquidity": "<raw liquidity from on-chain event>"
        },
        {
            "name": "LP2",
            "tick_lower": -12530,
            "tick_upper": 18970,
            "amount0": "150000",
            "amount1": "412678",
        },
    ],

    # Trades to simulate.
    # side = "token0_in" means: spend token0, receive token1
    # side = "token1_in" means: spend token1, receive token0
    # "trades": [
    #     {"side": "token0_in", "amount_in": "100"},
    #     {"side": "token0_in", "amount_in": "300"},
    #     {"side": "token0_in", "amount_in": "400"},
    #     {"side": "token0_in", "amount_in": "500"},
    #     {"side": "token0_in", "amount_in": "600"},
    #     {"side": "token0_in", "amount_in": "700"},
    #     {"side": "token0_in", "amount_in": "800"},
    #     {"side": "token0_in", "amount_in": "900"},
    # ],
    "trades": [
        {"side": "token0_in", "amount_in": "100000"},
        {"side": "token0_in", "amount_in": "200000"},
        {"side": "token0_in", "amount_in": "300000"},
        {"side": "token0_in", "amount_in": "400000"},
        {"side": "token0_in", "amount_in": "500000"},
    ],
}
# =======================
# Editable config ends here
# =======================


def D(x: Any) -> Decimal:
    return Decimal(str(x))


def sqrt_x96_to_sqrt_price(sqrt_x96: int | str) -> Decimal:
    return D(sqrt_x96) / Q96


def tick_to_sqrt_price(tick: int) -> Decimal:
    # Practical and readable; more than enough for quote work.
    return D(str(math.pow(1.0001, tick / 2)))


def sqrt_price_to_tick(sqrt_price: Decimal) -> int:
    price = float(sqrt_price * sqrt_price)
    return math.floor(math.log(price) / math.log(1.0001))


def human_to_raw(amount_human: str | int | float | Decimal, decimals: int) -> Decimal:
    return D(amount_human) * (Decimal(10) ** decimals)


def raw_to_human(amount_raw: Decimal, decimals: int) -> Decimal:
    return amount_raw / (Decimal(10) ** decimals)


def price_token1_per_token0(sqrt_price: Decimal, decimals0: int, decimals1: int) -> Decimal:
    # Chain raw price is token1_raw / token0_raw.
    # Convert to human units.
    return (sqrt_price * sqrt_price) * (Decimal(10) ** (decimals0 - decimals1))


def price_token0_per_token1(sqrt_price: Decimal, decimals0: int, decimals1: int) -> Decimal:
    p = price_token1_per_token0(sqrt_price, decimals0, decimals1)
    return Decimal(1) / p


def symbol_usd_price(config: Dict[str, Any], symbol: str) -> Optional[Decimal]:
    symbol_upper = symbol.upper()
    overrides = {str(k).upper(): v for k, v in dict(config.get("symbol_usd_price", {})).items()}

    if symbol_upper in overrides and overrides[symbol_upper] not in (None, ""):
        return D(overrides[symbol_upper])

    if symbol_upper in DEFAULT_STABLE_SYMBOLS:
        return Decimal(1)

    if symbol_upper in DEFAULT_BNB_SYMBOLS and config.get("BNB_PRICE") not in (None, ""):
        return D(config["BNB_PRICE"])

    return None


def derive_liquidity_from_amounts(
    amount0_raw: Decimal,
    amount1_raw: Decimal,
    sqrt_p: Decimal,
    sqrt_a: Decimal,
    sqrt_b: Decimal,
) -> Decimal:
    """
    Derive position liquidity from mint-time amounts and the current sqrt price
    at the moment the position was created.
    """
    if sqrt_p <= sqrt_a:
        return amount0_raw * sqrt_a * sqrt_b / (sqrt_b - sqrt_a)
    if sqrt_p >= sqrt_b:
        return amount1_raw / (sqrt_b - sqrt_a)

    candidates: List[Decimal] = []
    if amount0_raw > 0:
        l0 = amount0_raw * sqrt_p * sqrt_b / (sqrt_b - sqrt_p)
        candidates.append(l0)
    if amount1_raw > 0:
        l1 = amount1_raw / (sqrt_p - sqrt_a)
        candidates.append(l1)

    if not candidates:
        raise ValueError("Need amount0 or amount1 to derive liquidity")

    # Use min(...) to be robust against tiny rounding differences.
    return min(candidates)


def build_pool_state(config: Dict[str, Any]) -> Tuple[Decimal, int, Decimal, Dict[int, Decimal]]:
    sqrt_p = sqrt_x96_to_sqrt_price(config["sqrt_price_x96"])
    current_tick = int(config["current_tick"])
    decimals0 = int(config["decimals0"])
    decimals1 = int(config["decimals1"])

    tick_net: Dict[int, Decimal] = {}
    active_liquidity = Decimal(0)

    for pos in config["positions"]:
        tick_lower = int(pos["tick_lower"])
        tick_upper = int(pos["tick_upper"])
        sqrt_a = tick_to_sqrt_price(tick_lower)
        sqrt_b = tick_to_sqrt_price(tick_upper)

        if "liquidity" in pos and pos["liquidity"] not in (None, ""):
            liquidity = D(pos["liquidity"])
        else:
            amount0_raw = human_to_raw(pos.get("amount0", 0), decimals0)
            amount1_raw = human_to_raw(pos.get("amount1", 0), decimals1)
            liquidity = derive_liquidity_from_amounts(amount0_raw, amount1_raw, sqrt_p, sqrt_a, sqrt_b)

        tick_net[tick_lower] = tick_net.get(tick_lower, Decimal(0)) + liquidity
        tick_net[tick_upper] = tick_net.get(tick_upper, Decimal(0)) - liquidity

        if tick_lower <= current_tick < tick_upper:
            active_liquidity += liquidity

    return sqrt_p, current_tick, active_liquidity, tick_net


def quote_exact_in(config: Dict[str, Any], side: str, amount_in_human: str | int | float | Decimal) -> Dict[str, Decimal | int | str | None]:
    """
    Exact-input quote through a CLMM pool.

    side:
    - token0_in => spend token0, receive token1
    - token1_in => spend token1, receive token0
    """
    sqrt_p, current_tick, active_liquidity, tick_net = build_pool_state(config)
    decimals0 = int(config["decimals0"])
    decimals1 = int(config["decimals1"])
    fee_pips = D(config["fee_pips"])
    fee_factor = Decimal(1) - (fee_pips / Decimal(1_000_000))

    if side == "token0_in":
        amount_in_raw = human_to_raw(amount_in_human, decimals0)
        net_in_raw = amount_in_raw * fee_factor
        out_raw = Decimal(0)
        sorted_ticks = sorted(tick_net.keys())

        while net_in_raw > 0:
            if active_liquidity <= 0:
                raise RuntimeError("No active liquidity left while moving price downward")

            lower_ticks = [t for t in sorted_ticks if t < current_tick]
            if not lower_ticks:
                raise RuntimeError("Trade exhausts all lower active ranges; add more positions")

            next_tick = max(lower_ticks)
            sqrt_boundary = tick_to_sqrt_price(next_tick)

            dx_to_boundary = active_liquidity * (Decimal(1) / sqrt_boundary - Decimal(1) / sqrt_p)

            if net_in_raw < dx_to_boundary:
                sqrt_q = active_liquidity * sqrt_p / (active_liquidity + net_in_raw * sqrt_p)
                dy_out = active_liquidity * (sqrt_p - sqrt_q)
                out_raw += dy_out
                sqrt_p = sqrt_q
                net_in_raw = Decimal(0)
            else:
                dy_out = active_liquidity * (sqrt_p - sqrt_boundary)
                out_raw += dy_out
                net_in_raw -= dx_to_boundary
                sqrt_p = sqrt_boundary
                active_liquidity -= tick_net[next_tick]
                current_tick = next_tick - 1

        amount_out_human = raw_to_human(out_raw, decimals1)
        input_symbol = config["token0_symbol"]
        output_symbol = config["token1_symbol"]
        post_trade_spot_in_per_out = price_token0_per_token1(sqrt_p, decimals0, decimals1)

    elif side == "token1_in":
        amount_in_raw = human_to_raw(amount_in_human, decimals1)
        net_in_raw = amount_in_raw * fee_factor
        out_raw = Decimal(0)
        sorted_ticks = sorted(tick_net.keys())

        while net_in_raw > 0:
            if active_liquidity <= 0:
                raise RuntimeError("No active liquidity left while moving price upward")

            upper_ticks = [t for t in sorted_ticks if t > current_tick]
            if not upper_ticks:
                raise RuntimeError("Trade exhausts all upper active ranges; add more positions")

            next_tick = min(upper_ticks)
            sqrt_boundary = tick_to_sqrt_price(next_tick)

            dy_to_boundary = active_liquidity * (sqrt_boundary - sqrt_p)

            if net_in_raw < dy_to_boundary:
                sqrt_q = sqrt_p + (net_in_raw / active_liquidity)
                dx_out = active_liquidity * (Decimal(1) / sqrt_p - Decimal(1) / sqrt_q)
                out_raw += dx_out
                sqrt_p = sqrt_q
                net_in_raw = Decimal(0)
            else:
                dx_out = active_liquidity * (Decimal(1) / sqrt_p - Decimal(1) / sqrt_boundary)
                out_raw += dx_out
                net_in_raw -= dy_to_boundary
                sqrt_p = sqrt_boundary
                active_liquidity += tick_net[next_tick]
                current_tick = next_tick

        amount_out_human = raw_to_human(out_raw, decimals0)
        input_symbol = config["token1_symbol"]
        output_symbol = config["token0_symbol"]
        post_trade_spot_in_per_out = price_token1_per_token0(sqrt_p, decimals0, decimals1)

    else:
        raise ValueError("side must be 'token0_in' or 'token1_in'")

    avg_price_in_per_out = D(amount_in_human) / amount_out_human if amount_out_human != 0 else Decimal(0)
    input_usd_price = symbol_usd_price(config, str(input_symbol))
    avg_price_usd_per_out = avg_price_in_per_out * input_usd_price if input_usd_price is not None else None
    post_trade_spot_usd_per_out = post_trade_spot_in_per_out * input_usd_price if input_usd_price is not None else None
    end_tick = sqrt_price_to_tick(sqrt_p)

    return {
        "side": side,
        "amount_in": D(amount_in_human),
        "input_symbol": input_symbol,
        "amount_out": amount_out_human,
        "output_symbol": output_symbol,
        "avg_price_in_per_out": avg_price_in_per_out,
        "avg_price_usd_per_out": avg_price_usd_per_out,
        "post_trade_spot_in_per_out": post_trade_spot_in_per_out,
        "post_trade_spot_usd_per_out": post_trade_spot_usd_per_out,
        "input_symbol_usd_price": input_usd_price,
        "end_tick": end_tick,
        "end_price_token1_per_token0": price_token1_per_token0(sqrt_p, decimals0, decimals1),
        "end_price_token0_per_token1": price_token0_per_token1(sqrt_p, decimals0, decimals1),
    }


def fmt(x: Decimal, places: int = 8) -> str:
    q = Decimal(10) ** -places
    return format(x.quantize(q), "f")


def fmt_optional(x: Optional[Decimal], places: int = 8, blank: str = "-") -> str:
    if x is None:
        return blank
    return fmt(x, places)


def print_summary(config: Dict[str, Any]) -> None:
    sqrt_p = sqrt_x96_to_sqrt_price(config["sqrt_price_x96"])
    p10 = price_token1_per_token0(sqrt_p, config["decimals0"], config["decimals1"])
    p01 = price_token0_per_token1(sqrt_p, config["decimals0"], config["decimals1"])
    token0 = str(config["token0_symbol"])
    token1 = str(config["token1_symbol"])
    token0_usd = symbol_usd_price(config, token0)
    token1_usd = symbol_usd_price(config, token1)

    print("Pool summary")
    print("-" * 108)
    print(f"token0/token1: {token0}/{token1}")
    fee_pct = (Decimal(config['fee_pips']) / Decimal(1_000_000)) * Decimal(100)
    fee_bps = fee_pct * Decimal(100)
    print(f"fee_pips:      {config['fee_pips']}  ({fee_pct:.4f}% / {fee_bps:.2f} bps)")
    print(f"current_tick:  {config['current_tick']}")
    print(f"sqrtPriceX96:  {config['sqrt_price_x96']}")
    print(f"price:         1 {token0} = {fmt(p10, 8)} {token1}")
    print(f"price:         1 {token1} = {fmt(p01, 12)} {token0}")
    if token0_usd is not None:
        print(f"price:         1 {token1} = {fmt(p01 * token0_usd, 8)} USD  (via {token0}_PRICE)")
    elif token1_usd is not None and p10 != 0:
        print(f"price:         1 {token0} = {fmt(p10 * token1_usd, 8)} USD  (via {token1} USD price)")
    print()
    print("Price column meanings")
    print("- avg(native): average execution price in INPUT token / OUTPUT token")
    print("- end(native): post-trade spot price in INPUT token / OUTPUT token")
    print("- avg(USD):    average execution price in USD / OUTPUT token (if input token has USD price)")
    print("- end(USD):    post-trade spot price in USD / OUTPUT token (if input token has USD price)")
    print()


def print_trade_results(config: Dict[str, Any]) -> None:
    print_summary(config)
    print("Quotes")
    print("-" * 108)
    header = (
        f"{'side':<12} "
        f"{'amount_in':>20} "
        f"{'amount_out':>22} "
        f"{'avg(native)':>16} "
        f"{'avg(USD)':>14} "
        f"{'end(native)':>16} "
        f"{'end(USD)':>14} "
        f"{'end_tick':>10}"
    )
    print(header)
    print("-" * len(header))
    for trade in config["trades"]:
        res = quote_exact_in(config, trade["side"], trade["amount_in"])
        print(
            f"{res['side']:<12} "
            f"{(fmt(res['amount_in'], 8) + ' ' + str(res['input_symbol'])):>20} "
            f"{(fmt(res['amount_out'], 8) + ' ' + str(res['output_symbol'])):>22} "
            f"{fmt(res['avg_price_in_per_out'], 12):>16} "
            f"{fmt_optional(res['avg_price_usd_per_out'], 8):>14} "
            f"{fmt(res['post_trade_spot_in_per_out'], 12):>16} "
            f"{fmt_optional(res['post_trade_spot_usd_per_out'], 8):>14} "
            f"{str(res['end_tick']):>10}"
        )


if __name__ == "__main__":
    print_trade_results(CONFIG)
