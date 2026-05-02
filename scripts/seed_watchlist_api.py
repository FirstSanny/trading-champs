#!/usr/bin/env python3
"""
CI seed script — posts all watchlist symbols with full metadata to the deployed API.
Run by GitLab CI after each Vercel deployment.

Usage: python scripts/seed_watchlist_api.py <api_url> <api_key>

The API at <api_url>/api/watchlist/bulk accepts the same entry format as
the Supabase seed_watchlist.py — this script is the CI equivalent that
calls the deployed API instead of connecting to Supabase directly.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

SUPABASE_MIGRATION_URL = "https://{supabase_project_ref}.supabase.co/rest/v1/rpc/exec_sql"


def run_migrations(supabase_url: str, service_key: str) -> bool:
    """Apply all SQL migration files via Supabase management API.

    Uses the REST API to run each migration in order.
    Returns True if all migrations succeeded.
    """

    migrations_dir = os.path.join(os.path.dirname(__file__), "..", "supabase", "migrations")
    migration_files = sorted(f for f in os.listdir(migrations_dir) if f.endswith(".sql"))
    if not migration_files:
        print("No migration files found")
        return True

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    # Get Supabase project ref from URL
    # e.g. https://xyzabc.supabase.co → xyzabc
    project_ref = supabase_url.lstrip("https://").lstrip("http://").split(".")[0]
    exec_url = f"https://{project_ref}.supabase.co/rest/v1/rpc/exec_sql"

    applied = 0
    for mf in migration_files:
        path = os.path.join(migrations_dir, mf)
        sql = open(path).read()
        payload = json.dumps({"query": sql}).encode()
        req = urllib.request.Request(
            exec_url,
            data=payload,
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                if resp.status in (200, 201):
                    print(f"  {mf}: OK")
                    applied += 1
                else:
                    body = resp.read().decode()[:200]
                    print(f"  {mf}: HTTP {resp.status} — {body}")
                    return False
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            # 409 means migration already applied (idempotent via IF NOT EXISTS)
            if e.code == 409 or "already been applied" in body.lower():
                print(f"  {mf}: already applied (OK)")
                applied += 1
            else:
                print(f"  {mf}: HTTP {e.code} — {body}")
                return False
        except Exception as e:
            print(f"  {mf}: {e}")
            return False

    print(f"Applied {applied}/{len(migration_files)} migrations")
    return True


def wait_for_deployment(api_url: str, timeout: int = 60) -> bool:
    """Poll /api/watchlist until it responds, indicating the deployment is live."""
    health_url = f"{api_url.rstrip('/')}/api/watchlist"
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(health_url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(5)
    return False


SYMBOL_CATALOG = {
    "ASML": {
        "company_name": "ASML Holding N.V.",
        "category": "semiconductor",
        "description": "EUV lithography — every AI chip goes through ASML",
        "exchange": "NASDAQ",
    },
    "TSM": {
        "company_name": "Taiwan Semiconductor Manufacturing Co.",
        "category": "semiconductor",
        "description": "Foundry for AMD, Marvell, Nvidia",
        "exchange": "NYSE",
    },
    "LRCX": {
        "company_name": "Lam Research Corp.",
        "category": "semiconductor",
        "description": "Semiconductor fabrication equipment",
        "exchange": "NASDAQ",
    },
    "AMAT": {
        "company_name": "Applied Materials Inc.",
        "category": "semiconductor",
        "description": "Semiconductor fabrication equipment",
        "exchange": "NASDAQ",
    },
    "MRVL": {
        "company_name": "Marvell Technology Inc.",
        "category": "ai_chips",
        "description": "AI networking chips — 93% YTD",
        "exchange": "NASDAQ",
    },
    "AVGO": {
        "company_name": "Broadcom Inc.",
        "category": "ai_chips",
        "description": "AI networking and switching",
        "exchange": "NASDAQ",
    },
    "NVDA": {
        "company_name": "NVIDIA Corporation",
        "category": "ai_chips",
        "description": "AI GPU leader — H100/H200 dominance in data centers",
        "exchange": "NASDAQ",
    },
    "AMD": {
        "company_name": "Advanced Micro Devices Inc.",
        "category": "ai_chips",
        "description": "AI GPU competitor to Nvidia",
        "exchange": "NASDAQ",
    },
    "NBIS": {
        "company_name": "Nebius Group N.V.",
        "category": "ai_infra",
        "description": "Neocloud AI datacenter operator",
        "exchange": "NASDAQ",
    },
    "GLW": {
        "company_name": "Corning Inc.",
        "category": "ai_infra",
        "description": "Fiber optic cable for AI datacenters — 74% YTD",
        "exchange": "NYSE",
    },
    "ARM": {
        "company_name": "Arm Holdings plc",
        "category": "ai_infra",
        "description": "ARM architecture — mobile and edge AI",
        "exchange": "NASDAQ",
    },
    "GRPN": {
        "company_name": "Groupon Inc.",
        "category": "short_squeeze",
        "description": ">30% short interest, earnings May 6",
        "exchange": "NASDAQ",
    },
    "SOUN": {
        "company_name": "SoundHound AI Inc.",
        "category": "short_squeeze",
        "description": "Voice AI — earnings May 12",
        "exchange": "NASDAQ",
    },
    "LUNR": {
        "company_name": "Intuitive Machines Inc.",
        "category": "short_squeeze",
        "description": "Lunar exploration infrastructure",
        "exchange": "NASDAQ",
    },
    "DOCN": {
        "company_name": "DigitalOcean Holdings Inc.",
        "category": "short_squeeze",
        "description": "Cloud infrastructure for SMBs",
        "exchange": "NYSE",
    },
    "AMPX": {
        "company_name": "Amprius Technologies Inc.",
        "category": "short_squeeze",
        "description": "Lithium battery technology",
        "exchange": "NYSE",
    },
    "PATH": {
        "company_name": "Palantir Technologies Inc.",
        "category": "ai_software",
        "description": "AI and data analytics platform",
        "exchange": "NYSE",
    },
    "IONQ": {
        "company_name": "IonQ Inc.",
        "category": "ai_software",
        "description": "Quantum computing as a service",
        "exchange": "NYSE",
    },
    "CRWD": {
        "company_name": "CrowdStrike Holdings Inc.",
        "category": "ai_software",
        "description": "Cybersecurity AI platform",
        "exchange": "NASDAQ",
    },
    "SNOW": {
        "company_name": "Snowflake Inc.",
        "category": "ai_software",
        "description": "Data cloud and AI infrastructure",
        "exchange": "NYSE",
    },
    "DDOG": {
        "company_name": "Datadog Inc.",
        "category": "ai_software",
        "description": "Cloud monitoring and observability",
        "exchange": "NASDAQ",
    },
    "DKNG": {
        "company_name": "DraftKings Inc.",
        "category": "ai_software",
        "description": "Sports betting with AI personalization",
        "exchange": "NASDAQ",
    },
    "U": {
        "company_name": "Unity Software Inc.",
        "category": "ai_software",
        "description": "Gaming engine with AI content generation",
        "exchange": "NYSE",
    },
    "PLTR": {
        "company_name": "Palantir Technologies Inc.",
        "category": "ai_software",
        "description": "AI/Data analytics platform",
        "exchange": "NYSE",
    },
    "BABA": {
        "company_name": "Alibaba Group Holding Ltd.",
        "category": "chinese_tech",
        "description": "Cloud and AI — Alibaba Intelligence",
        "exchange": "NYSE",
    },
    "BIDU": {
        "company_name": "Baidu Inc.",
        "category": "chinese_tech",
        "description": "Search and AI — Ernie Bot",
        "exchange": "NASDAQ",
    },
    "JD": {
        "company_name": "JD.com Inc.",
        "category": "chinese_tech",
        "description": "E-commerce and AI logistics",
        "exchange": "NASDAQ",
    },
    "NTES": {
        "company_name": "NetEase Inc.",
        "category": "chinese_tech",
        "description": "Gaming and AI education",
        "exchange": "NASDAQ",
    },
    "PDD": {
        "company_name": "PDD Holdings Inc.",
        "category": "chinese_tech",
        "description": "Pinduoduo — e-commerce AI",
        "exchange": "NASDAQ",
    },
    "TCEHY": {
        "company_name": "Tencent Music Entertainment Group",
        "category": "chinese_tech",
        "description": "Tencent AI services",
        "exchange": "NYSE",
    },
    "XI": {
        "company_name": "Xiaomi Corp.",
        "category": "chinese_tech",
        "description": "Smartphones and AIoT ecosystem",
        "exchange": "HKEX",
    },
    "0100.HK": {
        "company_name": "MiniMax Inc.",
        "category": "chinese_ai_tiger",
        "description": "AI LLM — +109% debut Jan 9 2026",
        "exchange": "HKEX",
    },
    "2513.HK": {
        "company_name": "Zhipu AI",
        "category": "chinese_ai_tiger",
        "description": "AGI startup — +13% debut Jan 8 2026",
        "exchange": "HKEX",
    },
    "2080.HK": {
        "company_name": "01.AI (One AI)",
        "category": "chinese_ai_tiger",
        "description": "Yi-LLM developer",
        "exchange": "HKEX",
    },
    "IQ": {
        "company_name": "iQIYI Inc.",
        "category": "chinese_tech",
        "description": "Video streaming with AI dubbing",
        "exchange": "NASDAQ",
    },
    "BILI": {
        "company_name": "Bilibili Inc.",
        "category": "chinese_tech",
        "description": "Video and AI-powered content",
        "exchange": "NASDAQ",
    },
    "SMCI": {
        "company_name": "Super Micro Computer Inc.",
        "category": "ai_infra",
        "description": "AI server infrastructure",
        "exchange": "NYSE",
    },
    "COIN": {
        "company_name": "Coinbase Global Inc.",
        "category": "ai_crypto",
        "description": "Crypto exchange with AI trading tools",
        "exchange": "NASDAQ",
    },
    "MSTR": {
        "company_name": "MicroStrategy Inc.",
        "category": "ai_crypto",
        "description": "Bitcoin treasury with AI analytics",
        "exchange": "NASDAQ",
    },
    "FET/USDT": {
        "company_name": "Fetch.ai",
        "category": "ai_crypto",
        "description": "AI agents on blockchain",
        "exchange": "Binance",
    },
    "TAO/USDT": {
        "company_name": "Bittensor",
        "category": "ai_crypto",
        "description": "Decentralized AI network",
        "exchange": "Binance",
    },
    "RENDER/USDT": {
        "company_name": "Render Network",
        "category": "ai_crypto",
        "description": "GPU hosting for AI/ML workloads",
        "exchange": "Binance",
    },
    "WLD/USDT": {
        "company_name": "Worldcoin",
        "category": "ai_crypto",
        "description": "AI identity and privacy layer",
        "exchange": "Binance",
    },
    "JUP/USDT": {
        "company_name": "Jupiter",
        "category": "defi",
        "description": "Solana DEX aggregator",
        "exchange": "Binance",
    },
    "BLUR/USDT": {
        "company_name": "Blur",
        "category": "defi",
        "description": "NFT trading platform with AI tooling",
        "exchange": "Binance",
    },
    "TIA/USDT": {
        "company_name": "Celestia",
        "category": "blockchain_infra",
        "description": "Modular blockchain data availability",
        "exchange": "Binance",
    },
    "STX/USDT": {
        "company_name": "Stacks",
        "category": "blockchain_infra",
        "description": "Bitcoin L2 smart contracts",
        "exchange": "Binance",
    },
    "SUI/USDT": {
        "company_name": "Sui",
        "category": "blockchain_infra",
        "description": "L1 blockchain for AI apps",
        "exchange": "Binance",
    },
    "SEI/USDT": {
        "company_name": "Sei Network",
        "category": "blockchain_infra",
        "description": "Parallelized L1 for AI trading",
        "exchange": "Binance",
    },
    "BTC/USDT": {
        "company_name": "Bitcoin",
        "category": "ai_crypto",
        "description": "Store of value — AI settlement layer",
        "exchange": "Binance",
    },
    "ETH/USDT": {
        "company_name": "Ethereum",
        "category": "ai_crypto",
        "description": "Smart contract platform for AI agents",
        "exchange": "Binance",
    },
    "SOL/USDT": {
        "company_name": "Solana",
        "category": "ai_crypto",
        "description": "High-speed L1 for AI dapps",
        "exchange": "Binance",
    },
    "LINK/USDT": {
        "company_name": "Chainlink",
        "category": "ai_crypto",
        "description": "Decentralized oracles for AI data",
        "exchange": "Binance",
    },
    "SOXX": {
        "company_name": "iShares Semiconductor ETF",
        "category": "semiconductor_etf",
        "description": "Semiconductor industry exposure",
        "exchange": "NASDAQ",
    },
    "BOTZ": {
        "company_name": "Global X Robotics & AI ETF",
        "category": "robotics_etf",
        "description": "Robotics and AI automation",
        "exchange": "NASDAQ",
    },
    "ARKW": {
        "company_name": "ARK Next Generation Internet ETF",
        "category": "innovation_etf",
        "description": "Next-gen internet and AI",
        "exchange": "NASDAQ",
    },
    "IPO": {
        "company_name": "Renaissance IPO ETF",
        "category": "ipo_etf",
        "description": "Young public companies",
        "exchange": "NASDAQ",
    },
    "SKF": {
        "company_name": "ProShares Short Financials",
        "category": "sector_short",
        "description": "Financial sector short",
        "exchange": "NYSE",
    },
    "DRIP": {
        "company_name": "Direxion Daily Financial Bear 2x",
        "category": "sector_short",
        "description": "Financial sector 2x bearish",
        "exchange": "NYSE",
    },
}


def get_asset_class(symbol: str) -> str:
    if "/" in symbol:
        return "crypto"
    if symbol in ("SOXX", "BOTZ", "ARKW", "IPO", "SKF", "DRIP"):
        return "etf"
    return "stock"


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: seed_watchlist_api.py <api_url> <api_key> [supabase_service_key]")
        print(
            "  api_url — base URL of deployed API, e.g. https://trading-champs.vercel.app"
        )
        print("  api_key             — WATCHLIST_API_KEY value")
        print(
            "  supabase_service_key — optional; enables automatic Supabase migration before seeding"
        )
        sys.exit(1)

    api_url = sys.argv[1].rstrip("/")
    api_key = sys.argv[2]
    supabase_service_key = (
        sys.argv[3] if len(sys.argv) > 3 else os.environ.get("SUPABASE_SERVICE_KEY", "")
    )

    print(f"Waiting for deployment at {api_url} to be ready...")
    if not wait_for_deployment(api_url, timeout=90):
        print("Deployment not ready after 90s — skipping seed")
        sys.exit(0)

    if supabase_service_key:
        print("Applying Supabase migrations...")
        supabase_url = os.environ.get("SUPABASE_URL", "")
        if not run_migrations(supabase_url, supabase_service_key):
            print("WARNING: migrations failed — continuing anyway")

    print("Seeding watchlist symbols...")
    bulk_url = f"{api_url}/api/watchlist/bulk"

    entries = []
    for symbol, meta in SYMBOL_CATALOG.items():
        entries.append(
            {
                "symbol": symbol,
                "asset_class": get_asset_class(symbol),
                "metadata": {
                    "company_name": meta["company_name"],
                    "category": meta["category"],
                    "description": meta["description"],
                    "exchange": meta["exchange"],
                },
            }
        )

    payload = json.dumps({"added_by": "ci:seed-2026-05", "entries": entries}).encode()
    req = urllib.request.Request(
        bulk_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            added = result.get("added", 0)
            errors = result.get("errors", [])
            print(f"Seeded {added} symbols ({len(errors)} errors)")
            if errors:
                for err in errors[:5]:
                    print(f"  - {err}")
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"HTTP {e.code}: {body[:200]}")
        sys.exit(1)
    except Exception as e:
        print(f"Seed failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
