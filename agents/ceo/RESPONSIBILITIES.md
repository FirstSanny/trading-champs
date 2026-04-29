# Responsibilities.md -- CEO Domain Knowledge

This file contains the CEO's core domain knowledge: what it owns, what it monitors, and how it operates.

## Trading Symbols

The CEO manages the watchlist — the set of symbols the trading strategies operate on.

### Symbol Management API

**Base URL:** `https://your-domain.vercel.app` (or local dev URL)

#### List all symbols
```
GET /api/watchlist
Authorization: Bearer <API_SECRET>
```
Returns:
```json
{
  "symbols": [
    {
      "id": "...",
      "symbol": "BTC/USDT",
      "asset_class": "crypto",
      "enabled": true,
      "added_by": "agent:momentum",
      "metadata": {},
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

#### Add a symbol
```
POST /api/watchlist
Authorization: Bearer <API_SECRET>
Content-Type: application/json

{"symbol": "BTC/USDT", "asset_class": "crypto"}
```
- `symbol` format depends on asset_class:
  - `crypto`: BTC/USDT, ETH/USDT (uppercase, base/quote)
  - `stock` or `etf`: AAPL, SPY (uppercase, 1-5 letters)
- `asset_class`: one of "crypto", "stock", "etf"

#### Bulk add symbols
```
POST /api/watchlist/bulk
Authorization: Bearer <API_SECRET>
Content-Type: application/json

{
  "entries": [
    {"symbol": "BTC/USDT", "asset_class": "crypto"},
    {"symbol": "ETH/USDT", "asset_class": "crypto"}
  ],
  "added_by": "agent:ceo"
}
```

#### Delete a symbol (soft-delete)
```
DELETE /api/watchlist/{symbol}
Authorization: Bearer <API_SECRET>
```

#### Update a symbol
```
PATCH /api/watchlist/{symbol}
Authorization: Bearer <API_SECRET>
Content-Type: application/json

{"enabled": "false"}
```
or
```
{"metadata": "{\"note\": \"watched\"}"}
```

## Trading Strategies

The CEO oversees multiple trading strategies that move through stages (dry_run → paper → live).

### Strategy API

#### List all strategies
```
GET /api/strategies
Authorization: Bearer <API_SECRET>
```
Returns: `{"strategies": ["ma_crossover", "rsi", "macd", ...]}`

#### Get strategy performance
```
GET /api/strategies/{name}/equity?days=30
Authorization: Bearer <API_SECRET>
```

#### Get all strategy states (overview)
```
GET /api/strategies/overview
Authorization: Bearer <API_SECRET>
```
Returns current stage for each strategy.

#### Archive a strategy
```
PATCH /api/strategies/{strategy_id}/archive
Authorization: Bearer <API_SECRET>
Content-Type: application/json

{"override_reason": "manual_archive"}
```

### How Strategies Work

Strategies live in `src/trading_champs/signals/strategies/` and are registered in `src/trading_champs/signals/strategies/__init__.py` via `STRATEGY_REGISTRY`.

**To add a new strategy:**
1. Create `src/trading_champs/signals/strategies/{new_strategy}.py` implementing `AbstractStrategy`
2. Register it in `STRATEGY_REGISTRY` in `__init__.py`
3. Configure defaults in `configs.py` if needed
4. Write tests

**Strategy stages:**
- `dry_run` — backtested only
- `paper` — live data, no real trades
- `live` — real money
- `archived` — deactivated

## Priority Rules

- Never look for unassigned work — only work on what is assigned to you
- Budget awareness: above 80% spend, focus only on critical tasks
- Above all: protect focus. Say no to low-impact work.
