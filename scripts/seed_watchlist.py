#!/usr/bin/env python3
"""
Seed script to add recommended symbols to the watchlist.
Run: python scripts/seed_watchlist.py
Requires: SUPABASE_URL, SUPABASE_SERVICE_KEY environment variables.

SINGLE SOURCE OF TRUTH — SYMBOL_CATALOG
=======================================
This file is the authoritative source for all watchlist symbol metadata.
All other entry points (SQL migrations, API endpoints, CI jobs) should
use the values from this catalog as defaults.

Adding a new symbol:
1. Add entry to SYMBOL_CATALOG below with full metadata
2. Add to the appropriate category list (SEMICONDUCTOR_AI_STOCKS, etc.)
3. Run: python scripts/seed_watchlist.py
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from trading_champs.data.watchlist_repository import WatchlistRepository, get_watchlist_repository


def _check_env() -> None:
    """Fail fast if required env vars are missing."""
    missing = [k for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY") if not os.environ.get(k)]
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        print("Set SUPABASE_URL and SUPABASE_SERVICE_KEY before running this script.")
        sys.exit(1)


# =============================================================================
# SYMBOL CATALOG — Single Source of Truth
# =============================================================================
SYMBOL_CATALOG: dict[str, dict[str, str]] = {
    # Semiconductor / AI Infrastructure
    "ASML": {"company_name": "ASML Holding N.V.", "category": "semiconductor", "description": "EUV lithography — every AI chip goes through ASML", "exchange": "NASDAQ"},
    "TSM":  {"company_name": "Taiwan Semiconductor Manufacturing Co.", "category": "semiconductor", "description": "Foundry for AMD, Marvell, Nvidia", "exchange": "NYSE"},
    "LRCX": {"company_name": "Lam Research Corp.", "category": "semiconductor", "description": "Semiconductor fabrication equipment", "exchange": "NASDAQ"},
    "AMAT": {"company_name": "Applied Materials Inc.", "category": "semiconductor", "description": "Semiconductor fabrication equipment", "exchange": "NASDAQ"},
    "MRVL": {"company_name": "Marvell Technology Inc.", "category": "ai_chips", "description": "AI networking chips — 93% YTD", "exchange": "NASDAQ"},
    "AVGO": {"company_name": "Broadcom Inc.", "category": "ai_chips", "description": "AI networking and switching", "exchange": "NASDAQ"},
    "NVDA": {"company_name": "NVIDIA Corporation", "category": "ai_chips", "description": "AI GPU leader — H100/H200 dominance in data centers", "exchange": "NASDAQ"},
    "AMD":  {"company_name": "Advanced Micro Devices Inc.", "category": "ai_chips", "description": "AI GPU competitor to Nvidia", "exchange": "NASDAQ"},
    "NBIS": {"company_name": "Nebius Group N.V.", "category": "ai_infra", "description": "Neocloud AI datacenter operator", "exchange": "NASDAQ"},
    "GLW":  {"company_name": "Corning Inc.", "category": "ai_infra", "description": "Fiber optic cable for AI datacenters — 74% YTD", "exchange": "NYSE"},
    "ARM":  {"company_name": "Arm Holdings plc", "category": "ai_infra", "description": "ARM architecture — mobile and edge AI", "exchange": "NASDAQ"},

    # Short Squeeze Candidates
    "GRPN": {"company_name": "Groupon Inc.", "category": "short_squeeze", "description": ">30% short interest, earnings May 6", "exchange": "NASDAQ"},
    "SOUN": {"company_name": "SoundHound AI Inc.", "category": "short_squeeze", "description": "Voice AI — earnings May 12", "exchange": "NASDAQ"},
    "LUNR": {"company_name": "Intuitive Machines Inc.", "category": "short_squeeze", "description": "Lunar exploration infrastructure", "exchange": "NASDAQ"},
    "DOCN": {"company_name": "DigitalOcean Holdings Inc.", "category": "short_squeeze", "description": "Cloud infrastructure for SMBs", "exchange": "NYSE"},
    "AMPX": {"company_name": "Amprius Technologies Inc.", "category": "short_squeeze", "description": "Lithium battery technology", "exchange": "NYSE"},

    # AI Software / Cloud
    "IONQ": {"company_name": "IonQ Inc.", "category": "ai_software", "description": "Quantum computing as a service", "exchange": "NYSE"},
    "CRWD": {"company_name": "CrowdStrike Holdings Inc.", "category": "ai_software", "description": "Cybersecurity AI platform", "exchange": "NASDAQ"},
    "SNOW": {"company_name": "Snowflake Inc.", "category": "ai_software", "description": "Data cloud and AI infrastructure", "exchange": "NYSE"},
    "DDOG": {"company_name": "Datadog Inc.", "category": "ai_software", "description": "Cloud monitoring and observability", "exchange": "NASDAQ"},
    "DKNG": {"company_name": "DraftKings Inc.", "category": "ai_software", "description": "Sports betting with AI personalization", "exchange": "NASDAQ"},
    "U":    {"company_name": "Unity Software Inc.", "category": "ai_software", "description": "Gaming engine with AI content generation", "exchange": "NYSE"},
    "PLTR": {"company_name": "Palantir Technologies Inc.", "category": "ai_software", "description": "AI/Data analytics platform", "exchange": "NYSE"},

    # Chinese AI Stocks
    "BABA":  {"company_name": "Alibaba Group Holding Ltd.", "category": "chinese_tech", "description": "Cloud and AI — Alibaba Intelligence", "exchange": "NYSE"},
    "BIDU":  {"company_name": "Baidu Inc.", "category": "chinese_tech", "description": "Search and AI — Ernie Bot", "exchange": "NASDAQ"},
    "JD":    {"company_name": "JD.com Inc.", "category": "chinese_tech", "description": "E-commerce and AI logistics", "exchange": "NASDAQ"},
    "NTES":  {"company_name": "NetEase Inc.", "category": "chinese_tech", "description": "Gaming and AI education", "exchange": "NASDAQ"},
    "PDD":   {"company_name": "PDD Holdings Inc.", "category": "chinese_tech", "description": "Pinduoduo — e-commerce AI", "exchange": "NASDAQ"},
    "TCEHY": {"company_name": "Tencent Music Entertainment Group", "category": "chinese_tech", "description": "Tencent AI services", "exchange": "NYSE"},
    "XI":    {"company_name": "Xiaomi Corp.", "category": "chinese_tech", "description": "Smartphones and AIoT ecosystem", "exchange": "HKEX"},
    "0100.HK": {"company_name": "MiniMax Inc.", "category": "chinese_ai_tiger", "description": "AI LLM — +109% debut Jan 9 2026", "exchange": "HKEX"},
    "2513.HK": {"company_name": "Zhipu AI", "category": "chinese_ai_tiger", "description": "AGI startup — +13% debut Jan 8 2026", "exchange": "HKEX"},
    "2080.HK": {"company_name": "01.AI (One AI)", "category": "chinese_ai_tiger", "description": "Yi-LLM developer", "exchange": "HKEX"},
    "IQ":    {"company_name": "iQIYI Inc.", "category": "chinese_tech", "description": "Video streaming with AI dubbing", "exchange": "NASDAQ"},
    "BILI":  {"company_name": "Bilibili Inc.", "category": "chinese_tech", "description": "Video and AI-powered content", "exchange": "NASDAQ"},
    "DOYU":  {"company_name": "Douyu International Holdings", "category": "chinese_tech", "description": "Game streaming platform", "exchange": "NASDAQ"},
    "YY":    {"company_name": "YY Group", "category": "chinese_tech", "description": "Live streaming and video AI", "exchange": "NASDAQ"},
    "KEY":   {"company_name": "KE Holdings Inc.", "category": "chinese_tech", "description": "AI real estate platform (Beike)", "exchange": "NYSE"},
    "TAL":   {"company_name": "TAL Education Group", "category": "chinese_tech", "description": "AI-powered education", "exchange": "NYSE"},

    # Additional Growth
    "SMCI":  {"company_name": "Super Micro Computer Inc.", "category": "ai_infra", "description": "AI server infrastructure", "exchange": "NYSE"},
    "COIN":  {"company_name": "Coinbase Global Inc.", "category": "ai_crypto", "description": "Crypto exchange with AI trading tools", "exchange": "NASDAQ"},
    "MSTR":  {"company_name": "MicroStrategy Inc.", "category": "ai_crypto", "description": "Bitcoin treasury with AI analytics", "exchange": "NASDAQ"},

    # Crypto — AI / DeFi / Infra
    "FET/USDT":  {"company_name": "Fetch.ai", "category": "ai_crypto", "description": "AI agents on blockchain", "exchange": "Binance"},
    "TAO/USDT":  {"company_name": "Bittensor", "category": "ai_crypto", "description": "Decentralized AI network", "exchange": "Binance"},
    "RENDER/USDT": {"company_name": "Render Network", "category": "ai_crypto", "description": "GPU hosting for AI/ML workloads", "exchange": "Binance"},
    "WLD/USDT":  {"company_name": "Worldcoin", "category": "ai_crypto", "description": "AI identity and privacy layer", "exchange": "Binance"},
    "JUP/USDT":  {"company_name": "Jupiter", "category": "defi", "description": "Solana DEX aggregator", "exchange": "Binance"},
    "BLUR/USDT": {"company_name": "Blur", "category": "defi", "description": "NFT trading platform with AI tooling", "exchange": "Binance"},
    "TIA/USDT":  {"company_name": "Celestia", "category": "blockchain_infra", "description": "Modular blockchain data availability", "exchange": "Binance"},
    "STX/USDT":  {"company_name": "Stacks", "category": "blockchain_infra", "description": "Bitcoin L2 smart contracts", "exchange": "Binance"},
    "SUI/USDT":  {"company_name": "Sui", "category": "blockchain_infra", "description": "L1 blockchain for AI apps", "exchange": "Binance"},
    "SEI/USDT":  {"company_name": "Sei Network", "category": "blockchain_infra", "description": "Parallelized L1 for AI trading", "exchange": "Binance"},
    "BTC/USDT":  {"company_name": "Bitcoin", "category": "ai_crypto", "description": "Store of value — AI settlement layer", "exchange": "Binance"},
    "ETH/USDT":  {"company_name": "Ethereum", "category": "ai_crypto", "description": "Smart contract platform for AI agents", "exchange": "Binance"},
    "SOL/USDT":  {"company_name": "Solana", "category": "ai_crypto", "description": "High-speed L1 for AI dapps", "exchange": "Binance"},
    "LINK/USDT": {"company_name": "Chainlink", "category": "ai_crypto", "description": "Decentralized oracles for AI data", "exchange": "Binance"},

    # ETF
    "SOXX":  {"company_name": "iShares Semiconductor ETF", "category": "semiconductor_etf", "description": "Semiconductor industry exposure", "exchange": "NASDAQ"},
    "BOTZ":  {"company_name": "Global X Robotics & AI ETF", "category": "robotics_etf", "description": "Robotics and AI automation", "exchange": "NASDAQ"},
    "ARKW":  {"company_name": "ARK Next Generation Internet ETF", "category": "innovation_etf", "description": "Next-gen internet and AI", "exchange": "NASDAQ"},
    "IPO":   {"company_name": "Renaissance IPO ETF", "category": "ipo_etf", "description": "Young public companies", "exchange": "NASDAQ"},
    "SKF":   {"company_name": "ProShares Short Financials", "category": "sector_short", "description": "Financial sector short", "exchange": "NYSE"},
    "DRIP":  {"company_name": "Direxion Daily Financial Bear 2x", "category": "sector_short", "description": "Financial sector 2x bearish", "exchange": "NYSE"},
}


# =============================================================================
# CATEGORY LISTS — reference SYMBOL_CATALOG for metadata
# =============================================================================
SEMICONDUCTOR_AI_STOCKS = [
    ("ASML", "stock"), ("TSM", "stock"), ("LRCX", "stock"), ("AMAT", "stock"),
    ("MRVL", "stock"), ("AVGO", "stock"), ("NVDA", "stock"), ("AMD", "stock"),
    ("NBIS", "stock"), ("GLW", "stock"), ("ARM", "stock"),
]

SHORT_SQUEEZE_STOCKS = [
    ("GRPN", "stock"), ("SOUN", "stock"), ("LUNR", "stock"), ("DOCN", "stock"), ("AMPX", "stock"),
]

AI_SOFTWARE_STOCKS = [
    ("PLTR", "stock"), ("IONQ", "stock"), ("CRWD", "stock"), ("SNOW", "stock"),
    ("DDOG", "stock"), ("DKNG", "stock"), ("U", "stock"),
]

CHINESE_AI_STOCKS = [
    ("BABA", "stock"), ("BIDU", "stock"), ("JD", "stock"), ("NTES", "stock"),
    ("PDD", "stock"), ("TCEHY", "stock"), ("XI", "stock"),
    ("0100.HK", "stock"), ("2513.HK", "stock"), ("2080.HK", "stock"),
    ("IQ", "stock"), ("BILI", "stock"), ("DOYU", "stock"), ("YY", "stock"),
    ("KEY", "stock"), ("TAL", "stock"),
]

ADDITIONAL_STOCKS = [
    ("SMCI", "stock"), ("COIN", "stock"), ("MSTR", "stock"),
]

NEW_CRYPTO = [
    ("FET/USDT", "crypto"), ("TAO/USDT", "crypto"), ("RENDER/USDT", "crypto"),
    ("WLD/USDT", "crypto"), ("JUP/USDT", "crypto"), ("BLUR/USDT", "crypto"),
    ("TIA/USDT", "crypto"), ("STX/USDT", "crypto"), ("SUI/USDT", "crypto"),
    ("SEI/USDT", "crypto"), ("BTC/USDT", "crypto"), ("ETH/USDT", "crypto"),
    ("SOL/USDT", "crypto"), ("LINK/USDT", "crypto"),
]

NEW_ETF = [
    ("SOXX", "etf"), ("BOTZ", "etf"), ("ARKW", "etf"), ("IPO", "etf"), ("SKF", "etf"), ("DRIP", "etf"),
]


def add_symbols(name: str, symbols: list[tuple[str, str]], repo: WatchlistRepository):
    """Add symbols and return (added, skipped) count."""
    added = 0
    skipped = 0
    print(f"\n[ADD] {len(symbols)} {name}...")
    for symbol, asset_class in symbols:
        catalog = SYMBOL_CATALOG.get(symbol, {})
        metadata = {
            "company_name": catalog.get("company_name", ""),
            "category": catalog.get("category", ""),
            "description": catalog.get("description", ""),
            "exchange": catalog.get("exchange", ""),
        }
        try:
            result = repo.add_symbol(symbol, asset_class, added_by="seed:2026-05", metadata=metadata)
            if result:
                print(f"  + {symbol} ({metadata.get('company_name', '—')})")
                added += 1
            else:
                print(f"  ~ {symbol} (duplicate)")
                skipped += 1
        except Exception as e:
            print(f"  x {symbol}: {e}")
            skipped += 1
    return added, skipped


def main():
    _check_env()
    repo: WatchlistRepository = get_watchlist_repository()

    print("=" * 60)
    print("SEEDING WATCHLIST - AI-Focused Symbols (May 2026)")
    print("=" * 60)

    total_added = 0
    total_skipped = 0

    for name, stocks in [
        ("Semiconductor/AI Infrastructure", SEMICONDUCTOR_AI_STOCKS),
        ("Short Squeeze Candidates", SHORT_SQUEEZE_STOCKS),
        ("AI Software/Cloud", AI_SOFTWARE_STOCKS),
        ("Chinese AI Stocks", CHINESE_AI_STOCKS),
        ("Additional Growth", ADDITIONAL_STOCKS),
    ]:
        added, skipped = add_symbols(name, stocks, repo)
        total_added += added
        total_skipped += skipped

    added, skipped = add_symbols("Crypto (AI/DeFi)", NEW_CRYPTO, repo)
    total_added += added
    total_skipped += skipped

    added, skipped = add_symbols("ETF", NEW_ETF, repo)
    total_added += added
    total_skipped += skipped

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Symbols added: {total_added}")
    print(f"  Duplicates/skipped: {total_skipped}")
    print(f"  Total: {total_added + total_skipped}")


if __name__ == "__main__":
    main()