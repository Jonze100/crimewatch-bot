import aiohttp, logging, asyncio
logger = logging.getLogger(__name__)

# Binance known hot wallet addresses (ETH/ERC-20)
BINANCE_HOT_WALLETS = [
    "0x28C6c06298d514Db089934071355E5743bf21d60",  # Binance 14
    "0xdFd5293D8e347dFe59E90eFd55b2956a1343963D",  # Binance 15
    "0x56Eddb7aa87536c09CCc2793473599fD21A8b17F",  # Binance 16
    "0x21a31Ee1afC51d94C2efcCAa2092aD1028285549",  # Binance 17
    "0x9696f59E4d72E237BE84fFD425DCaD154Bf96976",  # Binance 18
    "0xB8c77482e45F1F44dE1745F52C74426C631bDD52",  # Binance token contract
    "0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503",  # Binance cold wallet
]

ETHERSCAN_BASE = "https://api.etherscan.io/v2/api"

async def get_token_supply(session, token_contract, api_key, chain_id=1):
    try:
        url = (f"{ETHERSCAN_BASE}?chainid={chain_id}&module=stats&action=tokensupply"
               f"&contractaddress={token_contract}&apikey={api_key}")
        async with session.get(url) as r:
            data = await r.json() if r.status == 200 else {}
        result = data.get("result", "0")
        return int(result) if str(result).isdigit() else 0
    except Exception as e:
        logger.warning(f"Supply fetch error: {e}"); return 0

async def get_recent_outflows(session, token_contract, api_key, chain_id=1):
    """Get large token transfers FROM Binance wallets in last 500 blocks (~1.5 hours)"""
    try:
        url = (f"{ETHERSCAN_BASE}?chainid={chain_id}&module=account&action=tokentx"
               f"&contractaddress={token_contract}&startblock=0&endblock=99999999"
               f"&sort=desc&apikey={api_key}")
        async with session.get(url) as r:
            data = await r.json() if r.status == 200 else {}
        txs = data.get("result", [])
        if not isinstance(txs, list): return []

        outflows = []
        for tx in txs[:50]:  # check last 50 transactions
            from_addr = tx.get("from", "").lower()
            is_binance_outflow = any(w.lower() == from_addr for w in BINANCE_HOT_WALLETS)
            if is_binance_outflow:
                decimals = int(tx.get("tokenDecimal", 18))
                value = int(tx.get("value", 0)) / (10 ** decimals)
                outflows.append({
                    "hash": tx.get("hash"),
                    "from": tx.get("from"),
                    "to": tx.get("to"),
                    "value": value,
                    "token": tx.get("tokenSymbol"),
                    "contract": token_contract,
                    "timestamp": int(tx.get("timeStamp", 0)),
                    "block": tx.get("blockNumber"),
                })
        return outflows
    except Exception as e:
        logger.warning(f"Outflow fetch error: {e}"); return []

async def check_whale_outflow(token_symbol, token_contract, api_key, chain_id=1):
    """
    Returns alert dict if suspicious outflow detected, else None.
    Flags if single wallet withdraws >3% of circulating supply.
    """
    async with aiohttp.ClientSession(
        headers={"User-Agent": "CrimeWatch/1.0"},
        timeout=aiohttp.ClientTimeout(total=15)
    ) as session:
        supply, outflows = await asyncio.gather(
            get_token_supply(session, token_contract, api_key, chain_id),
            get_recent_outflows(session, token_contract, api_key, chain_id)
        )

    if not outflows: return None

    alerts = []
    for tx in outflows:
        if supply > 0:
            pct = (tx["value"] / supply) * 100
        else:
            pct = 0

        # Flag if >3% of supply withdrawn in one tx, or >$500K equivalent
        if pct >= 3 or tx["value"] >= 500_000:
            alerts.append({
                "symbol": token_symbol,
                "contract": token_contract,
                "whale_address": tx["to"],
                "amount": tx["value"],
                "pct_supply": pct,
                "tx_hash": tx["hash"],
                "chain_id": chain_id,
            })

    return alerts[0] if alerts else None

# Token registry — symbol -> (contract, chain_id)
# chain_id 1 = Ethereum, 56 = BSC
TOKEN_REGISTRY = {
    "STOUSDT":   ("0x7D7b462A4C8f877Ed8FEe7bFBba1f53Fd4E2f2DA", 1),
    "ETHUSDT":   ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", 1),
    "BNBUSDT":   ("0xB8c77482e45F1F44dE1745F52C74426C631bDD52", 1),
    "UNIUSDT":   ("0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984", 1),
    "LINKUSDT":  ("0x514910771AF9Ca656af840dff83E8264EcF986CA", 1),
    "AAVEUSDT":  ("0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9", 1),
    "ONDOUSDT":  ("0xfAbA6f8e4a5E8Ab82F62fe7C39859FA577269BE3", 1),
    "SOLUSDT":   ("0xD31a59c85aE9D8edEFeC411D448f90841571b89c", 1),
    "PEPEUSDT":  ("0x6982508145454Ce325dDbE47a25d4ec3d2311933", 1),
    "WIFUSDT":   ("0x163f8C2467924be0ae7B5347228CABF260318753", 1),
}

async def scan_whale_activity(api_key):
    """Scan all known tokens for suspicious outflows"""
    findings = []
    for symbol, (contract, chain_id) in TOKEN_REGISTRY.items():
        try:
            alert = await check_whale_outflow(symbol, contract, api_key, chain_id)
            if alert:
                findings.append(alert)
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Whale scan error {symbol}: {e}")
    return findings
