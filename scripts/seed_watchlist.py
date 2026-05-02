#!/usr/bin/env python3
"""
Seed script to add recommended symbols to the watchlist.
Run: python scripts/seed_watchlist.py
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from trading_champs.data.watchlist_repository import WatchlistRepository, get_watchlist_repository


# =============================================================================
# NEW STOCKS - Semiconductor/AI Infrastructure
# =============================================================================
SEMICONDUCTOR_AI_STOCKS = [
    # EUV/Foundry
    ("ASML", "stock"),      # EUV Lithografie - jeder KI-Chip geht durch ASML
    ("TSM", "stock"),       # TSMC - Foundry für AMD, Marvell, Nvidia
    
    # Equipment
    ("LRCX", "stock"),      # Lam Research - Foundry Equipment
    ("AMAT", "stock"),      # Applied Materials - Semiconductor Equipment
    
    # AI Chips/Networking
    ("MRVL", "stock"),      # AI Networking Chips - 93% YTD
    ("AVGO", "stock"),      # Broadcom - AI Networking/Switching
    ("NVDA", "stock"),      # Nvidia - AI GPU (already in list but confirm)
    ("AMD", "stock"),       # AMD - AI GPU (already in list but confirm)
    
    # AI Infrastructure
    ("NBIS", "stock"),      # Nebius - Neocloud AI Datacenter
    ("GLW", "stock"),       # Corning - Glasfaser für AI Datacenter - 74% YTD
    
    # ARM Architecture
    ("ARM", "stock"),       # ARM Architecture - Mobile AI
]

# =============================================================================
# SHORT SQUEEZE CANDIDATES
# =============================================================================
SHORT_SQUEEZE_STOCKS = [
    ("GRPN", "stock"),      # Groupon - >30% SI, Earnings May 6
    ("SOUN", "stock"),      # SoundHound AI - Earnings May 12
    ("LUNR", "stock"),      # Intuitive Machines - Satellite
    ("DOCN", "stock"),      # DigitalOcean - Cloud
    ("AMPX", "stock"),      # Amprius - Lithium Battery
]

# =============================================================================
# AI SOFTWARE/CLOUD
# =============================================================================
AI_SOFTWARE_STOCKS = [
    ("PATH", "stock"),      # Palantir - AI/Data Analytics
    ("IONQ", "stock"),      # Quantum Computing
    ("CRWD", "stock"),      # CrowdStrike - Cybersecurity AI
    ("SNOW", "stock"),      # Snowflake - Data Cloud
    ("DDOG", "stock"),      # Datadog - Cloud Monitoring
    ("DKNG", "stock"),      # DraftKings - Sports betting AI
    ("U", "stock"),         # Unity - Gaming/AI
    ("PLTR", "stock"),      # Palantir (already in list)
]

# =============================================================================
# CHINESE AI STOCKS (US ADRs & Hong Kong)
# =============================================================================
CHINESE_AI_STOCKS = [
    # BATX - Major Chinese Tech
    ("BABA", "stock"),      # Alibaba - Cloud & AI
    ("BIDU", "stock"),      # Baidu - Search & AI (Ernie Bot)
    ("JD", "stock"),        # JD.com - E-commerce & AI
    ("NTES", "stock"),      # NetEase - Gaming & AI
    ("PDD", "stock"),       # Pinduoduo - E-commerce AI
    ("TCEHY", "stock"),     # Tencent ADR
    ("XI", "stock"),        # Xiaomi ADR
    
    # Chinese AI Players (listed in US)
    ("IQ", "stock"),        # iQIYI - Video/AI
    ("MNSO", "stock"),      # MiHoYo - Gaming (private, skip if needed)
    
    # Chinese Cloud/AI
    ("KEY", "stock"),       # KE Holdings (Beike) - AI Real Estate
    ("TAL", "stock"),       # TAL Education - AI Education
    ("BILI", "stock"),      # Bilibili - Video/AI
    ("DOYU", "stock"),      # Douyu - Gaming
    ("YY", "stock"),        # YY - Live Streaming
]

# =============================================================================
# ADDITIONAL GROWTH STOCKS
# =============================================================================
ADDITIONAL_STOCKS = [
    ("SMCI", "stock"),      # Super Micro Computer - already in list
    ("COIN", "stock"),      # Coinbase - Crypto (already in list)
    ("MSTR", "stock"),      # MicroStrategy - Bitcoin
]

# =============================================================================
# NEW CRYPTO - AI + DeFi + RWA
# =============================================================================
NEW_CRYPTO = [
    # AI Crypto
    ("FET/USDT", "crypto"),   # Fetch.ai - AI Agenten auf Blockchain
    ("TAO/USDT", "crypto"),   # Bittensor - Dezentrales KI-Netzwerk
    ("RENDER/USDT", "crypto"),# Render - GPU Hosting für AI/ML
    ("WLD/USDT", "crypto"),   # Worldcoin - AI Identity Layer
    
    # DeFi
    ("JUP/USDT", "crypto"),   # Jupiter - Solana DEX Aggregator
    ("BLUR/USDT", "crypto"),  # Blur - NFT Trading Platform
    
    # Modular/Infra
    ("TIA/USDT", "crypto"),   # Celestia - Modular Blockchain Data Availability
    ("STX/USDT", "crypto"),   # Stacks - Bitcoin L2 Smart Contracts
    ("SUI/USDT", "crypto"),   # Sui - L1 Blockchain
    ("SEI/USDT", "crypto"),   # Sei - Parallelized L1
    
    # Already in watchlist (confirm/update)
    ("BTC/USDT", "crypto"),
    ("ETH/USDT", "crypto"),
    ("SOL/USDT", "crypto"),
    ("LINK/USDT", "crypto"),
]

# =============================================================================
# NEW ETF
# =============================================================================
NEW_ETF = [
    ("SOXX", "etf"),    # Semiconductor ETF
    ("BOTZ", "etf"),    # Robotik & AI
    ("ARKW", "etf"),    # ARK Next Generation Internet
    ("IPO", "etf"),     # IPO ETF - junge Unternehmen
    ("SKF", "etf"),     # Finanz-Sektor short
    ("DRIP", "etf"),    # Financial Sector Bear 2x
]


def add_symbols(name: str, symbols: list[tuple[str, str]], repo: WatchlistRepository):
    """Add symbols and return count."""
    added = 0
    skipped = 0
    print(f"\n📈 Adding {len(symbols)} {name}...")
    for symbol, asset_class in symbols:
        try:
            result = repo.add_symbol(symbol, asset_class, added_by="seed:2026-05")
            if result:
                print(f"  ✅ {symbol}")
                added += 1
            else:
                print(f"  ⚠️  {symbol} (duplicate)")
                skipped += 1
        except Exception as e:
            print(f"  ❌ {symbol}: {e}")
            skipped += 1
    return added, skipped


def main():
    repo: WatchlistRepository = get_watchlist_repository()
    
    print("=" * 60)
    print("SEEDING WATCHLIST - AI-Focused Symbols (May 2026)")
    print("=" * 60)
    
    total_added = 0
    total_skipped = 0
    
    # Add all stock categories
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
    
    # Add crypto
    added, skipped = add_symbols("Crypto (AI/DeFi)", NEW_CRYPTO, repo)
    total_added += added
    total_skipped += skipped
    
    # Add ETF
    added, skipped = add_symbols("ETF", NEW_ETF, repo)
    total_added += added
    total_skipped += skipped
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  ✅ Symbols added: {total_added}")
    print(f"  ⚠️  Duplicates/skipped: {total_skipped}")
    print(f"  📊 Total: {total_added + total_skipped}")


if __name__ == "__main__":
    main()