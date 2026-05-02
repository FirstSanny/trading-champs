-- Seed watchlist symbols for Trading Champs
-- Run: Apply this migration after 002_watchlist_symbols.sql

BEGIN;

-- Clear existing data (optional - comment out if you want to keep existing)
-- DELETE FROM watchlist_symbols WHERE true;

-- =============================================================================
-- SEMICONDUCTOR / AI INFRASTRUCTURE
-- =============================================================================
INSERT INTO watchlist_symbols (symbol, asset_class, enabled, added_by, metadata) VALUES
('ASML', 'stock', true, 'migration:2026-05-02', '{"category": "semiconductor", "reason": "EUV lithography - every AI chip goes through ASML"}'),
('TSM', 'stock', true, 'migration:2026-05-02', '{"category": "semiconductor", "reason": "Foundry for AMD, Marvell, Nvidia"}'),
('LRCX', 'stock', true, 'migration:2026-05-02', '{"category": "semiconductor", "reason": "Lam Research - Foundry Equipment"}'),
('AMAT', 'stock', true, 'migration:2026-05-02', '{"category": "semiconductor", "reason": "Applied Materials - Semiconductor Equipment"}'),
('MRVL', 'stock', true, 'migration:2026-05-02', '{"category": "ai_chips", "reason": "AI Networking Chips - 93% YTD"}'),
('AVGO', 'stock', true, 'migration:2026-05-02', '{"category": "ai_chips", "reason": "Broadcom - AI Networking/Switching"}'),
('NVDA', 'stock', true, 'migration:2026-05-02', '{"category": "ai_chips", "reason": "Nvidia - AI GPU leader"}'),
('AMD', 'stock', true, 'migration:2026-05-02', '{"category": "ai_chips", "reason": "AMD - AI GPU competitor"}'),
('NBIS', 'stock', true, 'migration:2026-05-02', '{"category": "ai_infra", "reason": "Nebius - Neocloud AI Datacenter"}'),
('GLW', 'stock', true, 'migration:2026-05-02', '{"category": "ai_infra", "reason": "Corning - Fiber for AI Datacenter - 74% YTD"}'),
('ARM', 'stock', true, 'migration:2026-05-02', '{"category": "ai_infra", "reason": "ARM Architecture - Mobile AI"}')
ON CONFLICT (symbol) DO NOTHING;

-- =============================================================================
-- SHORT SQUEEZE CANDIDATES
-- =============================================================================
INSERT INTO watchlist_symbols (symbol, asset_class, enabled, added_by, metadata) VALUES
('GRPN', 'stock', true, 'migration:2026-05-02', '{"category": "short_squeeze", "reason": ">30% SI, Earnings May 6"}'),
('SOUN', 'stock', true, 'migration:2026-05-02', '{"category": "short_squeeze", "reason": "SoundHound AI - Earnings May 12"}'),
('LUNR', 'stock', true, 'migration:2026-05-02', '{"category": "short_squeeze", "reason": "Intuitive Machines - Satellite"}'),
('DOCN', 'stock', true, 'migration:2026-05-02', '{"category": "short_squeeze", "reason": "DigitalOcean - Cloud"}'),
('AMPX', 'stock', true, 'migration:2026-05-02', '{"category": "short_squeeze", "reason": "Amprius - Lithium Battery"}')
ON CONFLICT (symbol) DO NOTHING;

-- =============================================================================
-- AI SOFTWARE / CLOUD
-- =============================================================================
INSERT INTO watchlist_symbols (symbol, asset_class, enabled, added_by, metadata) VALUES
('PATH', 'stock', true, 'migration:2026-05-02', '{"category": "ai_software", "reason": "Palantir - AI/Data Analytics"}'),
('IONQ', 'stock', true, 'migration:2026-05-02', '{"category": "ai_software", "reason": "Quantum Computing"}'),
('CRWD', 'stock', true, 'migration:2026-05-02', '{"category": "ai_software", "reason": "CrowdStrike - Cybersecurity AI"}'),
('SNOW', 'stock', true, 'migration:2026-05-02', '{"category": "ai_software", "reason": "Snowflake - Data Cloud"}'),
('DDOG', 'stock', true, 'migration:2026-05-02', '{"category": "ai_software", "reason": "Datadog - Cloud Monitoring"}'),
('DKNG', 'stock', true, 'migration:2026-05-02', '{"category": "ai_software", "reason": "DraftKings - Sports betting AI"}'),
('U', 'stock', true, 'migration:2026-05-02', '{"category": "ai_software", "reason": "Unity - Gaming/AI"}')
ON CONFLICT (symbol) DO NOTHING;

-- =============================================================================
-- CHINESE AI STOCKS (BATX + AI Tigers)
-- =============================================================================
INSERT INTO watchlist_symbols (symbol, asset_class, enabled, added_by, metadata) VALUES
('BABA', 'stock', true, 'migration:2026-05-02', '{"category": "chinese_tech", "reason": "Alibaba - Cloud & AI"}'),
('BIDU', 'stock', true, 'migration:2026-05-02', '{"category": "chinese_tech", "reason": "Baidu - Ernie Bot"}'),
('JD', 'stock', true, 'migration:2026-05-02', '{"category": "chinese_tech", "reason": "JD.com - E-commerce & AI"}'),
('NTES', 'stock', true, 'migration:2026-05-02', '{"category": "chinese_tech", "reason": "NetEase - Gaming & AI"}'),
('PDD', 'stock', true, 'migration:2026-05-02', '{"category": "chinese_tech", "reason": "Pinduoduo - E-commerce AI"}'),
('TCEHY', 'stock', true, 'migration:2026-05-02', '{"category": "chinese_tech", "reason": "Tencent ADR"}'),
('XI', 'stock', true, 'migration:2026-05-02', '{"category": "chinese_tech", "reason": "Xiaomi ADR"}'),
-- AI Tigers - Hong Kong IPOs Jan 2026
('0100.HK', 'stock', true, 'migration:2026-05-02', '{"category": "chinese_ai_tiger", "reason": "MiniMax - AI LLM, +109% debut Jan 9, 2026"}'),
('2513.HK', 'stock', true, 'migration:2026-05-02', '{"category": "chinese_ai_tiger", "reason": "Zhipu AI - AGI, +13% debut Jan 8, 2026"}'),
('2080.HK', 'stock', true, 'migration:2026-05-02', '{"category": "chinese_ai_tiger", "reason": "01.AI (One AI) - Yi-LLM"}'),
-- Other Chinese
('IQ', 'stock', true, 'migration:2026-05-02', '{"category": "chinese_tech", "reason": "iQIYI - Video/AI"}'),
('BILI', 'stock', true, 'migration:2026-05-02', '{"category": "chinese_tech", "reason": "Bilibili - Video/AI"}')
ON CONFLICT (symbol) DO NOTHING;

-- =============================================================================
-- CRYPTO - AI / DEFI / INFRA
-- =============================================================================
INSERT INTO watchlist_symbols (symbol, asset_class, enabled, added_by, metadata) VALUES
('FET/USDT', 'crypto', true, 'migration:2026-05-02', '{"category": "ai_crypto", "reason": "Fetch.ai - AI Agents on Blockchain"}'),
('TAO/USDT', 'crypto', true, 'migration:2026-05-02', '{"category": "ai_crypto", "reason": "Bittensor - Decentralized AI Network"}'),
('RENDER/USDT', 'crypto', true, 'migration:2026-05-02', '{"category": "ai_crypto", "reason": "Render - GPU Hosting for AI/ML"}'),
('WLD/USDT', 'crypto', true, 'migration:2026-05-02', '{"category": "ai_crypto", "reason": "Worldcoin - AI Identity Layer"}'),
('JUP/USDT', 'crypto', true, 'migration:2026-05-02', '{"category": "defi", "reason": "Jupiter - Solana DEX Aggregator"}'),
('BLUR/USDT', 'crypto', true, 'migration:2026-05-02', '{"category": "defi", "reason": "Blur - NFT Trading Platform"}'),
('TIA/USDT', 'crypto', true, 'migration:2026-05-02', '{"category": "blockchain_infra", "reason": "Celestia - Modular Blockchain DA"}'),
('STX/USDT', 'crypto', true, 'migration:2026-05-02', '{"category": "blockchain_infra", "reason": "Stacks - Bitcoin L2 Smart Contracts"}'),
('SUI/USDT', 'crypto', true, 'migration:2026-05-02', '{"category": "blockchain_infra", "reason": "Sui - L1 Blockchain"}'),
('SEI/USDT', 'crypto', true, 'migration:2026-05-02', '{"category": "blockchain_infra", "reason": "Sei - Parallelized L1"}')
ON CONFLICT (symbol) DO NOTHING;

-- =============================================================================
-- ETF
-- =============================================================================
INSERT INTO watchlist_symbols (symbol, asset_class, enabled, added_by, metadata) VALUES
('SOXX', 'etf', true, 'migration:2026-05-02', '{"category": "semiconductor_etf", "reason": "Semiconductor ETF"}'),
('BOTZ', 'etf', true, 'migration:2026-05-02', '{"category": "robotics_etf", "reason": "Robotics & AI ETF"}'),
('ARKW', 'etf', true, 'migration:2026-05-02', '{"category": "innovation_etf", "reason": "ARK Next Generation Internet"}'),
('IPO', 'etf', true, 'migration:2026-05-02', '{"category": "ipo_etf", "reason": "IPO ETF - Young Companies"}'),
('SKF', 'etf', true, 'migration:2026-05-02', '{"category": "sector_short", "reason": "Financial Sector Short"}'),
('DRIP', 'etf', true, 'migration:2026-05-02', '{"category": "sector_short", "reason": "Financial Sector Bear 2x"}')
ON CONFLICT (symbol) DO NOTHING;

COMMIT;