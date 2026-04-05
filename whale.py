import aiohttp, logging, asyncio
logger = logging.getLogger(__name__)

BINANCE_HOT_WALLETS = [
    "0x28C6c06298d514Db089934071355E5743bf21d60",
    "0xdFd5293D8e347dFe59E90eFd55b2956a1343963D",
    "0x56Eddb7aa87536c09CCc2793473599fD21A8b17F",
    "0x21a31Ee1afC51d94C2efcCAa2092aD1028285549",
    "0x9696f59E4d72E237BE84fFD425DCaD154Bf96976",
    "0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503",
    "0xF977814e90dA44bFA03b6295A0616a897441aceC",
    "0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8",
    "0x5a52E96BAcdaBb82fd05763E25335261B270Efcb",
    "0x3c783C21A0383057D128bae431894a5C19F9Cf06",
]

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
ETHERSCAN_BASE = "https://api.etherscan.io/v2/api"

contract_cache = {}

async def get_contract_address(session, symbol):
    clean = symbol.replace("USDT", "").lower()
    if clean in contract_cache:
        return contract_cache[clean]
    try:
        async with session.get(f"{COINGECKO_BASE}/search?query={clean}") as r:
            data = await r.json() if r.status == 200 else {}
        coins = data.get("coins", [])
        match = next((c for c in coins if c.get("symbol","").lower() == clean), None)
        if not match:
            contract_cache[clean] = None
            return None
        coin_id = match["id"]
        url2 = (f"{COINGECKO_BASE}/coins/{coin_id}"
                f"?localization=false&tickers=false&market_data=false"
                f"&community_data=false&developer_data=false")
        async with session.get(url2) as r:
            detail = await r.json() if r.status == 200 else {}
        platforms = detail.get("detail_platforms") or detail.get("platforms", {})
        contract, chain_id = None, 1
        eth = platforms.get("ethereum")
        bsc = platforms.get("binance-smart-chain")
        if eth:
            contract = eth.get("contract_address") if isinstance(eth, dict) else eth
            chain_id = 1
        elif bsc:
            contract = bsc.get("contract_address") if isinstance(bsc, dict) else bsc
            chain_id = 56
        if contract:
            contract_cache[clean] = (contract, chain_id)
            return (contract, chain_id)
    except Exception as e:
        logger.warning(f"CoinGecko lookup error {symbol}: {e}")
    contract_cache[clean] = None
    return None

async def get_token_supply(session, contract, api_key, chain_id):
    try:
        url = (f"{ETHERSCAN_BASE}?chainid={chain_id}&module=stats"
               f"&action=tokensupply&contractaddress={contract}&apikey={api_key}")
        async with session.get(url) as r:
            data = await r.json() if r.status == 200 else {}
        result = data.get("result", "0")
        return int(result) if str(result).isdigit() else 0
    except Exception as e:
        logger.warning(f"Supply fetch error: {e}"); return 0

async def get_recent_outflows(session, contract, api_key, chain_id):
    try:
        url = (f"{ETHERSCAN_BASE}?chainid={chain_id}&module=account"
               f"&action=tokentx&contractaddress={contract}"
               f"&startblock=0&endblock=99999999&sort=desc&apikey={api_key}")
        async with session.get(url) as r:
            data = await r.json() if r.status == 200 else {}
        txs = data.get("result", [])
        if not isinstance(txs, list): return []
        outflows = []
        for tx in txs[:100]:
            from_addr = tx.get("from", "").lower()
            if any(w.lower() == from_addr for w in BINANCE_HOT_WALLETS):
                decimals = int(tx.get("tokenDecimal", 18))
                value = int(tx.get("value", 0)) / (10 ** decimals)
                outflows.append({
                    "hash": tx.get("hash"),
                    "from": tx.get("from"),
                    "to": tx.get("to"),
                    "value": value,
                    "token": tx.get("tokenSymbol"),
                    "timestamp": int(tx.get("timeStamp", 0)),
                })
        return outflows
    except Exception as e:
        logger.warning(f"Outflow fetch error: {e}"); return []

async def scan_whale_activity(symbols, api_key):
    findings = []
    alerted_hashes = set()

    async with aiohttp.ClientSession(
        headers={"User-Agent": "CrimeWatch/1.0"},
        timeout=aiohttp.ClientTimeout(total=20)
    ) as session:
        logger.info(f"Resolving contracts for {len(symbols)} tokens...")
        contracts = {}
        for symbol in symbols:
            result = await get_contract_address(session, symbol)
            if result:
                contracts[symbol] = result
            await asyncio.sleep(1.5)  # CoinGecko free tier: max 30 req/min

        logger.info(f"Resolved {len(contracts)}/{len(symbols)} contracts. Scanning outflows...")

        for symbol, (contract, chain_id) in contracts.items():
            try:
                supply, outflows = await asyncio.gather(
                    get_token_supply(session, contract, api_key, chain_id),
                    get_recent_outflows(session, contract, api_key, chain_id)
                )
                for tx in outflows:
                    if tx["hash"] in alerted_hashes:
                        continue
                    pct = (tx["value"] / supply * 100) if supply > 0 else 0
                    if pct >= 3 or tx["value"] >= 500_000:
                        alerted_hashes.add(tx["hash"])
                        findings.append({
                            "symbol": symbol,
                            "contract": contract,
                            "whale_address": tx["to"],
                            "from_address": tx["from"],
                            "amount": tx["value"],
                            "pct_supply": pct,
                            "tx_hash": tx["hash"],
                            "chain_id": chain_id,
                            "timestamp": tx["timestamp"],
                        })
                        logger.info(f"WHALE: {symbol} — {pct:.1f}% withdrawn")
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Whale scan error {symbol}: {e}")

    return findings
