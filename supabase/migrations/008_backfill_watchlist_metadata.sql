-- Backfill metadata for watchlist symbols that have empty metadata.
-- Metadata is sourced from SYMBOL_CATALOG in seed_watchlist_api.py.

BEGIN;

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "ASML Holding N.V.",
  "category": "semiconductor",
  "description": "EUV lithography — every AI chip goes through ASML",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'ASML';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Taiwan Semiconductor Manufacturing Co.",
  "category": "semiconductor",
  "description": "Foundry for AMD, Marvell, Nvidia",
  "exchange": "NYSE"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'TSM';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Lam Research Corp.",
  "category": "semiconductor",
  "description": "Semiconductor fabrication equipment",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'LRCX';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Applied Materials Inc.",
  "category": "semiconductor",
  "description": "Semiconductor fabrication equipment",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'AMAT';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Marvell Technology Inc.",
  "category": "ai_chips",
  "description": "AI networking chips — 93% YTD",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'MRVL';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Broadcom Inc.",
  "category": "ai_chips",
  "description": "AI networking and switching",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'AVGO';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "NVIDIA Corporation",
  "category": "ai_chips",
  "description": "AI GPU leader — H100/H200 dominance in data centers",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'NVDA';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Advanced Micro Devices Inc.",
  "category": "ai_chips",
  "description": "AI GPU competitor to Nvidia",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'AMD';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Nebius Group N.V.",
  "category": "ai_infra",
  "description": "Neocloud AI datacenter operator",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'NBIS';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Corning Inc.",
  "category": "ai_infra",
  "description": "Fiber optic cable for AI datacenters — 74% YTD",
  "exchange": "NYSE"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'GLW';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Arm Holdings plc",
  "category": "ai_infra",
  "description": "ARM architecture — mobile and edge AI",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'ARM';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Groupon Inc.",
  "category": "short_squeeze",
  "description": ">30% short interest, earnings May 6",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'GRPN';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "SoundHound AI Inc.",
  "category": "short_squeeze",
  "description": "Voice AI — earnings May 12",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'SOUN';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Intuitive Machines Inc.",
  "category": "short_squeeze",
  "description": "Lunar exploration infrastructure",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'LUNR';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "DigitalOcean Holdings Inc.",
  "category": "short_squeeze",
  "description": "Cloud infrastructure for SMBs",
  "exchange": "NYSE"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'DOCN';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Amprius Technologies Inc.",
  "category": "short_squeeze",
  "description": "Lithium battery technology",
  "exchange": "NYSE"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'AMPX';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "IonQ Inc.",
  "category": "ai_software",
  "description": "Quantum computing as a service",
  "exchange": "NYSE"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'IONQ';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "CrowdStrike Holdings Inc.",
  "category": "ai_software",
  "description": "Cybersecurity AI platform",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'CRWD';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Snowflake Inc.",
  "category": "ai_software",
  "description": "Data cloud and AI infrastructure",
  "exchange": "NYSE"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'SNOW';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Datadog Inc.",
  "category": "ai_software",
  "description": "Cloud monitoring and observability",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'DDOG';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "DraftKings Inc.",
  "category": "ai_software",
  "description": "Sports betting with AI personalization",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'DKNG';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Unity Software Inc.",
  "category": "ai_software",
  "description": "Gaming engine with AI content generation",
  "exchange": "NYSE"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'U';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Palantir Technologies Inc.",
  "category": "ai_software",
  "description": "AI/Data analytics platform",
  "exchange": "NYSE"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'PLTR';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Alibaba Group Holding Ltd.",
  "category": "chinese_tech",
  "description": "Cloud and AI — Alibaba Intelligence",
  "exchange": "NYSE"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'BABA';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Baidu Inc.",
  "category": "chinese_tech",
  "description": "Search and AI — Ernie Bot",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'BIDU';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "JD.com Inc.",
  "category": "chinese_tech",
  "description": "E-commerce and AI logistics",
  "exchange": "NYSE"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'JD';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "NetEase Inc.",
  "category": "chinese_tech",
  "description": "Gaming and AI education",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'NTES';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "PDD Holdings Inc.",
  "category": "chinese_tech",
  "description": "Pinduoduo — e-commerce AI",
  "exchange": "NYSE"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'PDD';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Tencent Music Entertainment Group",
  "category": "chinese_tech",
  "description": "Tencent AI services",
  "exchange": "NYSE"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'TCEHY';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Xiaomi Corp.",
  "category": "chinese_tech",
  "description": "Smartphones and AIoT ecosystem",
  "exchange": "HKEX"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'XI';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "MiniMax Inc.",
  "category": "chinese_ai_tiger",
  "description": "AI LLM — +109% debut Jan 9 2026",
  "exchange": "HKEX"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = '0100.HK';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Zhipu AI",
  "category": "chinese_ai_tiger",
  "description": "AGI startup — +13% debut Jan 8 2026",
  "exchange": "HKEX"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = '2513.HK';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "01.AI (One AI)",
  "category": "chinese_ai_tiger",
  "description": "Yi-LLM developer",
  "exchange": "HKEX"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = '2080.HK';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "iQIYI Inc.",
  "category": "chinese_tech",
  "description": "Video streaming with AI dubbing",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'IQ';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Bilibili Inc.",
  "category": "chinese_tech",
  "description": "Video and AI-powered content",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'BILI';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Super Micro Computer Inc.",
  "category": "ai_infra",
  "description": "AI server infrastructure",
  "exchange": "NYSE"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'SMCI';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Coinbase Global Inc.",
  "category": "ai_crypto",
  "description": "Crypto exchange with AI trading tools",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'COIN';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "MicroStrategy Inc.",
  "category": "ai_crypto",
  "description": "Bitcoin treasury with AI analytics",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'MSTR';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Fetch.ai",
  "category": "ai_crypto",
  "description": "AI agents on blockchain",
  "exchange": "Binance"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'FET/USDT';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Bittensor",
  "category": "ai_crypto",
  "description": "Decentralized AI network",
  "exchange": "Binance"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'TAO/USDT';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Render Network",
  "category": "ai_crypto",
  "description": "GPU hosting for AI/ML workloads",
  "exchange": "Binance"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'RENDER/USDT';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Worldcoin",
  "category": "ai_crypto",
  "description": "AI identity and privacy layer",
  "exchange": "Binance"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'WLD/USDT';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Jupiter",
  "category": "defi",
  "description": "Solana DEX aggregator",
  "exchange": "Binance"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'JUP/USDT';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Blur",
  "category": "defi",
  "description": "NFT trading platform with AI tooling",
  "exchange": "Binance"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'BLUR/USDT';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Celestia",
  "category": "blockchain_infra",
  "description": "Modular blockchain data availability",
  "exchange": "Binance"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'TIA/USDT';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Stacks",
  "category": "blockchain_infra",
  "description": "Bitcoin L2 smart contracts",
  "exchange": "Binance"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'STX/USDT';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Sui",
  "category": "blockchain_infra",
  "description": "L1 blockchain for AI apps",
  "exchange": "Binance"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'SUI/USDT';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Sei Network",
  "category": "blockchain_infra",
  "description": "Parallelized L1 for AI trading",
  "exchange": "Binance"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'SEI/USDT';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Bitcoin",
  "category": "ai_crypto",
  "description": "Store of value — AI settlement layer",
  "exchange": "Binance"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'BTC/USDT';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Ethereum",
  "category": "ai_crypto",
  "description": "Smart contract platform for AI agents",
  "exchange": "Binance"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'ETH/USDT';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Solana",
  "category": "ai_crypto",
  "description": "High-speed L1 for AI dapps",
  "exchange": "Binance"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'SOL/USDT';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Chainlink",
  "category": "ai_crypto",
  "description": "Decentralized oracles for AI data",
  "exchange": "Binance"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'LINK/USDT';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "iShares Semiconductor ETF",
  "category": "semiconductor_etf",
  "description": "Semiconductor industry exposure",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'SOXX';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Global X Robotics & AI ETF",
  "category": "robotics_etf",
  "description": "Robotics and AI automation",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'BOTZ';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "ARK Next Generation Internet ETF",
  "category": "innovation_etf",
  "description": "Next-gen internet and AI",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'ARKW';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Renaissance IPO ETF",
  "category": "ipo_etf",
  "description": "Young public companies",
  "exchange": "NASDAQ"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'IPO';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "ProShares Short Financials",
  "category": "sector_short",
  "description": "Financial sector short",
  "exchange": "NYSE"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'SKF';

UPDATE watchlist_symbols
SET metadata = jsonb_strip_nulls(metadata || '{
  "company_name": "Direxion Daily Financial Bear 2x",
  "category": "sector_short",
  "description": "Financial sector 2x bearish",
  "exchange": "NYSE"
}'::jsonb)
WHERE deleted_at IS NULL
  AND metadata = '{}'::jsonb
  AND symbol = 'DRIP';

COMMIT;
