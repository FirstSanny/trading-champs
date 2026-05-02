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
# NEW STOCKS - Semiconductor/AI + Short Squeeze Candidates
# =============================================================================
NEW_STOCKS = [
    # Semiconductor/AI Infrastructure
    ("ASML", "stock"),      # EUV Lithografie - jeder KI-Chip geht durch ASML
    ("MRVL", "stock"),      # AI Networking Chips - 93% YTD
    ("AVGO", "stock"),      # Broadcom - AI Networking/Switching
    ("TSM", "stock"),       # TSMC - Foundry für AMD, Marvell, Nvidia
    ("NBIS", "stock"),      # Nebius - Neocloud AI Datacenter
    ("GLW", "stock"),       # Corning - Glasfaser für AI Datacenter - 74% YTD
    ("LRCX", "stock"),      # Lam Research - Foundry Equipment
    ("AMAT", "stock"),      # Applied Materials - Semiconductor Equipment
    
    # Short Squeeze Candidates
    ("GRPN", "stock"),      # Groupon - >30% SI, Earnings May 6
    ("SOUN", "stock"),      # SoundHound AI - Earnings May 12
    ("LUNR", "stock"),      # Intuitive Machines - Satellite
    ("DOCN", "stock"),      # DigitalOcean - Cloud
    ("AMPX", "stock"),      # Amprius - Lithium Battery
    
    # AI Cloud/Software
    ("IONQ", "stock"),      # Quantum Computing
    ("PATH", "stock"),      # Palantir - AI/Data Analytics
    ("DKNG", "stock"),      # DraftKings - Sports betting
    
    # Additional Watchlist-Worthy
    ("ARM", "stock"),       # ARM Architecture - Mobile AI
    ("CRWD", "stock"),      # CrowdStrike - Cybersecurity AI
    ("SNOW", "stock"),      # Snowflake - Data Cloud
    ("DDOG", "stock"),      # Datadog - Cloud Monitoring
]

# =============================================================================
# NEW CRYPTO - AI + DeFi + RWA
# =============================================================================
NEW_CRYPTO = [
    ("FET/USDT", "crypto"),   # Fetch.ai - AI Agenten auf Blockchain
    ("TAO/USDT", "crypto"),   # Bittensor - Dezentrales KI-Netzwerk
    ("RENDER/USDT", "crypto"),# Render - GPU Hosting für AI/ML
    ("WLD/USDT", "crypto"),   # Worldcoin - AI Identity Layer
    ("JUP/USDT", "crypto"),   # Jupiter - Solana DEX Aggregator
    ("TIA/USDT", "crypto"),   # Celestia - Modular Blockchain
    ("BLUR/USDT", "crypto"),  # Blur - NFT Trading Platform
    ("STX/USDT", "crypto"),   # Stacks - Bitcoin L2 Smart Contracts
    ("SUI/USDT", "crypto"),   # Sui - L1 Blockchain
    ("SEI/USDT", "crypto"),   # Sei - Parallelized L1
    ("TIA/USDT", "crypto"),   # Celestia - Modular Blockchain Data Availability
    ("WLD/USDT", "crypto"),   # Worldcoin - AI Identity
]

# =============================================================================
# NEW ETF
# =============================================================================
NEW_ETF = [
    ("SOXX", "etf"),    # Semiconductor ETF
    ("BOTZ", "etf"),    # Robotik & AI
    ("IPO", "etf"),     # IPO ETF - junge Unternehmen
    ("SKF", "etf"),     # Finanz-Sektor short
    ("DRIP", "etf"),    # Financial Sector Bear 2x
]


def main():
    repo: WatchlistRepository = get_watchlist_repository()
    
    print("=" * 60)
    print("SEEDING WATCHLIST - Trading Champs Symbols")
    print("=" * 60)
    
    added_stocks = 0
    added_crypto = 0
    added_etf = 0
    skipped = 0
    
    # Add stocks
    print(f"\n📈 Adding {len(NEW_STOCKS)} stocks...")
    for symbol, asset_class in NEW_STOCKS:
        try:
            result = repo.add_symbol(symbol, asset_class, added_by="seed:2026-05")
            if result:
                print(f"  ✅ {symbol}")
                added_stocks += 1
            else:
                print(f"  ⚠️  {symbol} (duplicate or error)")
                skipped += 1
        except Exception as e:
            print(f"  ❌ {symbol}: {e}")
            skipped += 1
    
    # Add crypto
    print(f"\n🪙 Adding {len(NEW_CRYPTO)} crypto...")
    for symbol, asset_class in NEW_CRYPTO:
        try:
            result = repo.add_symbol(symbol, asset_class, added_by="seed:2026-05")
            if result:
                print(f"  ✅ {symbol}")
                added_crypto += 1
            else:
                print(f"  ⚠️  {symbol} (duplicate or error)")
                skipped += 1
        except Exception as e:
            print(f"  ❌ {symbol}: {e}")
            skipped += 1
    
    # Add ETF
    print(f"\n📊 Adding {len(NEW_ETF)} ETF...")
    for symbol, asset_class in NEW_ETF:
        try:
            result = repo.add_symbol(symbol, asset_class, added_by="seed:2026-05")
            if result:
                print(f"  ✅ {symbol}")
                added_etf += 1
            else:
                print(f"  ⚠️  {symbol} (duplicate or error)")
                skipped += 1
        except Exception as e:
            print(f"  ❌ {symbol}: {e}")
            skipped += 1
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  ✅ Stocks added: {added_stocks}")
    print(f"  ✅ Crypto added: {added_crypto}")
    print(f"  ✅ ETF added: {added_etf}")
    print(f"  ⚠️  Skipped (duplicate): {skipped}")
    print(f"  📊 Total new symbols: {added_stocks + added_crypto + added_etf}")


if __name__ == "__main__":
    main()
