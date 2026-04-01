import time
import requests
from web3 import Web3
from eth_account import Account

ACROSS_API = "https://app.across.to/api"

BASE_CHAIN_ID = 8453
ETH_CHAIN_ID = 1

BASE_WETH = Web3.to_checksum_address("0x4200000000000000000000000000000000000006")
ETH_WETH = Web3.to_checksum_address("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")

BASE_SPOKE_POOL = Web3.to_checksum_address("0x09aea4b2242abC8bb4BB78D537A67a245A7bEC64")
ETH_SPOKE_POOL = Web3.to_checksum_address("0x5c7BCd6E7De5423a257D81B442095A1a6ced35C5")

SPOKE_POOL_ABI = [
    {
        "type": "function",
        "name": "depositV3",
        "stateMutability": "payable",
        "inputs": [
            {"name": "depositor", "type": "address"},
            {"name": "recipient", "type": "address"},
            {"name": "inputToken", "type": "address"},
            {"name": "outputToken", "type": "address"},
            {"name": "inputAmount", "type": "uint256"},
            {"name": "outputAmount", "type": "uint256"},
            {"name": "destinationChainId", "type": "uint256"},
            {"name": "exclusiveRelayer", "type": "address"},
            {"name": "quoteTimestamp", "type": "uint32"},
            {"name": "fillDeadline", "type": "uint32"},
            {"name": "exclusivityDeadline", "type": "uint32"},
            {"name": "message", "type": "bytes"},
        ],
        "outputs": [],
    },

    # ✅ 新增：V3FundsDeposited event（用来拿 depositId）
    {
        "type": "event",
        "name": "V3FundsDeposited",
        "anonymous": False,
        "inputs": [
            {"indexed": False, "name": "inputToken", "type": "address"},
            {"indexed": False, "name": "outputToken", "type": "address"},
            {"indexed": False, "name": "inputAmount", "type": "uint256"},
            {"indexed": False, "name": "outputAmount", "type": "uint256"},
            {"indexed": True, "name": "destinationChainId", "type": "uint256"},
            {"indexed": True, "name": "depositId", "type": "uint32"},
            {"indexed": False, "name": "quoteTimestamp", "type": "uint32"},
            {"indexed": False, "name": "fillDeadline", "type": "uint32"},
            {"indexed": False, "name": "exclusivityDeadline", "type": "uint32"},
            {"indexed": True, "name": "depositor", "type": "address"},
            {"indexed": False, "name": "recipient", "type": "address"},
            {"indexed": False, "name": "exclusiveRelayer", "type": "address"},
            {"indexed": False, "name": "message", "type": "bytes"},
        ],
    },

    # ✅ 新增：FundsDeposited（现在真正会 emit 的事件）
    {
        "type": "event",
        "name": "FundsDeposited",
        "anonymous": False,
        "inputs": [
            {"indexed": False, "name": "inputToken", "type": "bytes32"},
            {"indexed": False, "name": "outputToken", "type": "bytes32"},
            {"indexed": False, "name": "inputAmount", "type": "uint256"},
            {"indexed": False, "name": "outputAmount", "type": "uint256"},
            {"indexed": True, "name": "destinationChainId", "type": "uint256"},
            {"indexed": True, "name": "depositId", "type": "uint256"},
            {"indexed": False, "name": "quoteTimestamp", "type": "uint32"},
            {"indexed": False, "name": "fillDeadline", "type": "uint32"},
            {"indexed": False, "name": "exclusivityDeadline", "type": "uint32"},
            {"indexed": True, "name": "depositor", "type": "bytes32"},
            {"indexed": False, "name": "recipient", "type": "bytes32"},
            {"indexed": False, "name": "exclusiveRelayer", "type": "bytes32"},
            {"indexed": False, "name": "message", "type": "bytes"},
        ],
    },
]


def _eip1559_fees(w3: Web3, priority_gwei: int = 1, max_fee_mult: int = 2):
    # Base 和主网都支持 EIP-1559；如果某些 RPC 不给 baseFee，就 fallback legacy
    try:
        blk = w3.eth.get_block("pending")
        base_fee = blk.get("baseFeePerGas")
        if base_fee is None:
            raise RuntimeError("no baseFeePerGas")
        prio = w3.to_wei(priority_gwei, "gwei")
        max_fee = int(base_fee) * max_fee_mult + prio
        return {"maxFeePerGas": int(max_fee), "maxPriorityFeePerGas": int(prio)}
    except Exception:
        return {"gasPrice": int(w3.eth.gas_price)}


def across_suggested_fees(input_token, output_token, origin_chain_id, destination_chain_id, amount_wei, recipient):
    r = requests.get(
        f"{ACROSS_API}/suggested-fees",
        params={
            "inputToken": input_token,
            "outputToken": output_token,
            "originChainId": origin_chain_id,
            "destinationChainId": destination_chain_id,
            "amount": str(amount_wei),
            "recipient": recipient,
        },
        timeout=25,
    )
    if r.status_code != 200:
        raise RuntimeError(f"/suggested-fees failed {r.status_code}: {r.text}")
    return r.json()


def across_deposit_status(origin_chain_id: int, deposit_id: int):
    r = requests.get(
        f"{ACROSS_API}/deposit/status",
        params={"originChainId": str(origin_chain_id), "depositId": str(deposit_id)},
        timeout=25,
    )
    # 注意：有时刚发完 Across 还没 index，会 404 DepositNotFoundException
    if r.status_code == 404:
        return {"status": "not_indexed_yet", "raw": r.text}
    if r.status_code != 200:
        raise RuntimeError(f"/deposit/status failed {r.status_code}: {r.text}")
    return r.json()


def get_deposit_id_from_receipt(w3: Web3, spoke_pool: str, tx_hash: str, timeout=120):
    c = w3.eth.contract(address=Web3.to_checksum_address(spoke_pool), abi=SPOKE_POOL_ABI)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)

    # ✅ 1) 先用真正会 emit 的 FundsDeposited(bytes32...) 取 depositId(uint256 indexed)
    try:
        logs1 = c.events.FundsDeposited().process_receipt(receipt)
        if logs1:
            ev = logs1[0]
            deposit_id = int(ev["args"]["depositId"])
            return deposit_id, receipt
    except Exception:
        pass

    # ✅ 2) fallback：旧版本/其它链可能还会有 V3FundsDeposited(address...)（legacy）
    try:
        logs2 = c.events.V3FundsDeposited().process_receipt(receipt)
        if logs2:
            ev = logs2[0]
            deposit_id = int(ev["args"]["depositId"])
            return deposit_id, receipt
    except Exception:
        pass

    raise RuntimeError(f"FundsDeposited/V3FundsDeposited not found in receipt: {tx_hash}")



def wait_until_filled(origin_chain_id: int, deposit_id: int, poll=8, timeout=1800):
    start = time.time()
    while True:
        st = across_deposit_status(origin_chain_id, deposit_id)

        if st.get("status") == "filled":
            return st

        # not indexed yet / pending / etc
        if time.time() - start > timeout:
            raise TimeoutError(
                f"wait fill timeout: originChainId={origin_chain_id} depositId={deposit_id}, last={st.get('status')}")

        time.sleep(poll)


def across_deposit_v3_native_eth(
        w3: Web3,
        spoke_pool: str,
        private_key: str,
        *,
        origin_chain_id: int,
        destination_chain_id: int,
        input_weth: str,
        output_weth: str,
        amount_wei: int,
        priority_gwei: float = 1.0,
        gas_buffer_mult: float = 1.20,
):
    acct = Account.from_key(private_key)
    addr = acct.address

    quote = across_suggested_fees(
        input_token=input_weth,
        output_token=output_weth,
        origin_chain_id=origin_chain_id,
        destination_chain_id=destination_chain_id,
        amount_wei=amount_wei,
        recipient=addr,
    )

    if quote.get("isAmountTooLow") is True:
        limits = quote.get("limits", {})
        raise RuntimeError(f"amount too low, minDeposit={limits.get('minDeposit')} amount={amount_wei}")

    output_amount = int(quote["outputAmount"])
    exclusive_relayer = Web3.to_checksum_address(quote["exclusiveRelayer"])
    quote_ts = int(quote["timestamp"])
    fill_deadline = int(quote["fillDeadline"])
    exclusivity_deadline = int(quote.get("exclusivityDeadline", 0))

    c = w3.eth.contract(address=Web3.to_checksum_address(spoke_pool), abi=SPOKE_POOL_ABI)
    fn = c.functions.depositV3(
        Web3.to_checksum_address(addr),  # depositor
        Web3.to_checksum_address(addr),  # recipient
        Web3.to_checksum_address(input_weth),
        Web3.to_checksum_address(output_weth),
        int(amount_wei),
        int(output_amount),
        int(destination_chain_id),
        exclusive_relayer,
        int(quote_ts),
        int(fill_deadline),
        int(exclusivity_deadline),
        b"",
    )

    nonce = w3.eth.get_transaction_count(addr)
    fees = _eip1559_fees(w3, priority_gwei=priority_gwei)

    base_tx = {
        "from": addr,
        "nonce": nonce,
        "chainId": w3.eth.chain_id,
        "value": int(amount_wei),  # 原生 ETH 作为 msg.value
        **fees,
    }

    try:
        gas_est = fn.estimate_gas(base_tx)
        gas_limit = int(gas_est * gas_buffer_mult)
    except Exception:
        gas_limit = 350_000

    tx = fn.build_transaction({**base_tx, "gas": gas_limit})
    signed = Account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    return tx_hash.hex()


def get_eth_balance(w3: Web3, addr: str) -> int:
    return int(w3.eth.get_balance(Web3.to_checksum_address(addr)))


# =========================
# 你要改的循环：按你原来的风格
# =========================


from fun.base_init import w3 as w3_base
from fun.init import w3 as w3_eth

assert w3_base.eth.chain_id == BASE_CHAIN_ID
assert w3_eth.eth.chain_id == ETH_CHAIN_ID

bridge_amount_wei = Web3.to_wei(0.1, "ether")  # Base -> 主网 0.1 ETH（你可改）
eth_reserve_wei = Web3.to_wei(0.0001, "ether")  # 主网留 0.003 ETH 做 gas（你可改）
poll_seconds = 8
timeout_seconds = 1800

from fun.wallets import get_wallet_info

group_wallets = get_wallet_info()
# group_wallets = group_wallets[:1]
for item in group_wallets:
    addr = item["address"]
    pk = item["private_key"]

    try:
        # 1) Base -> Ethereum
        tx1 = across_deposit_v3_native_eth(
            w3_base,
            BASE_SPOKE_POOL,
            pk,
            origin_chain_id=BASE_CHAIN_ID,
            destination_chain_id=ETH_CHAIN_ID,
            input_weth=BASE_WETH,
            output_weth=ETH_WETH,
            amount_wei=bridge_amount_wei,
            priority_gwei=0.1,
        )
        print("Base->ETH tx:", addr, tx1)

        # 2) 等待第一段 fill 完成（Across API）
        deposit_id_1, receipt1 = get_deposit_id_from_receipt(w3_base, BASE_SPOKE_POOL, tx1, timeout=120)
        print("depositId1:", addr, deposit_id_1)

        st1 = wait_until_filled(BASE_CHAIN_ID, deposit_id_1, poll=poll_seconds, timeout=timeout_seconds)
        print("filled1:", addr, st1.get("fillTxnRef"))

        # 3) 计算回程金额（主网余额 - reserve）
        bal = get_eth_balance(w3_eth, addr)
        back_amount = bal - eth_reserve_wei
        if back_amount <= 0:
            print("skip return, mainnet balance too low:", addr, "bal", bal)
            time.sleep(3)
            continue

        # 4) Ethereum -> Base
        tx2 = across_deposit_v3_native_eth(
            w3_eth,
            ETH_SPOKE_POOL,
            pk,
            origin_chain_id=ETH_CHAIN_ID,
            destination_chain_id=BASE_CHAIN_ID,
            input_weth=ETH_WETH,
            output_weth=BASE_WETH,
            amount_wei=back_amount,
            priority_gwei=0.1,
        )
        print("ETH->Base tx:", addr, tx2)

        # （可选）等回程 fill
        deposit_id_2, receipt2 = get_deposit_id_from_receipt(w3_eth, ETH_SPOKE_POOL, tx2, timeout=180)
        st2 = wait_until_filled(ETH_CHAIN_ID, deposit_id_2, poll=poll_seconds, timeout=timeout_seconds)

    except Exception as e:
        print("ERROR:", addr, str(e))

    time.sleep(3)
