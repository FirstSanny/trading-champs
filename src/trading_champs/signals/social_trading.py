"""Social trading strategies - follow other traders."""

import random
from datetime import datetime, timedelta
from typing import Optional

from trading_champs.pl.tracker import TradeSide


class SocialTrader:
    """Simulates a social trading feed for demo purposes.

    In production, this would connect to a social trading API (e.g., eToro, ZuluTrade).
    For now, it generates mock signals based on the trader's chosen personas.
    """

    # Mock trading personas with their typical trade patterns
    PERSONAS = {
        "trumps_son": {
            "name": "Donald Trump Jr.",
            "style": "momentum",
            "win_rate": 0.52,
            "avg_trade_pct": 2.5,
            "symbols": ["DJT", "SPY", "QQQ", "AAPL", "MSFT", "BTC"],
            "side_bias": "long",
        },
        "wall_street_退休": {
            "name": "Wall Street Retiree",
            "style": "contrarian",
            "win_rate": 0.55,
            "avg_trade_pct": 1.5,
            "symbols": ["SPY", "Bonds", "GLD", "TLT"],
            "side_bias": "short",
        },
        "crypto_maximalist": {
            "name": "Crypto Maximalist",
            "style": "momentum",
            "win_rate": 0.48,
            "avg_trade_pct": 5.0,
            "symbols": ["BTC", "ETH", "SOL", "DOGE"],
            "side_bias": "long",
        },
    }

    def __init__(self, persona: str = "trumps_son"):
        """Initialize social trader with a persona.

        Args:
            persona: Key from PERSONAS dict (e.g., 'trumps_son')
        """
        self.persona = persona
        self.config = self.PERSONAS.get(persona, self.PERSONAS["trumps_son"])

    def get_signal(self, symbol: str, market_data: Optional[dict] = None) -> dict | None:
        """Get a trading signal for a symbol.

        Args:
            symbol: Trading symbol.
            market_data: Optional market context (price, volume, etc.)

        Returns:
            Dict with signal details or None if no signal.
        """
        # Only generate signals for this trader's preferred symbols
        if symbol not in self.config["symbols"]:
            return None

        # Simulate randomness with win rate
        if random.random() > self.config["win_rate"]:
            return None

        # Determine side based on bias and market data
        if self.config["side_bias"] == "random":
            side = random.choice([TradeSide.LONG, TradeSide.SHORT])
        elif self.config["side_bias"] == "long":
            side = TradeSide.LONG
        else:
            side = TradeSide.SHORT

        # Generate mock entry price
        base_price = market_data.get("price", 100.0) if market_data else 100.0
        price_change = base_price * (self.config["avg_trade_pct"] / 100)
        if side == TradeSide.LONG:
            entry_price = base_price * 1.02  # Slight rise
        else:
            entry_price = base_price * 0.98  # Slight drop

        return {
            "trader": self.config["name"],
            "persona": self.persona,
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "confidence": random.uniform(0.6, 0.95),
            "reason": f"Following {self.config['name']} ({self.config['style']} style)",
            "timestamp": datetime.now().isoformat(),
        }

    def get_recent_trades(self, limit: int = 10) -> list[dict]:
        """Get mock recent trades from this trader.

        Returns:
            List of mock trade dicts.
        """
        trades = []
        now = datetime.now()

        for i in range(limit):
            symbol = random.choice(self.config["symbols"])
            side = TradeSide.LONG if self.config["side_bias"] == "long" else TradeSide.SHORT
            if random.random() < 0.3:
                side = TradeSide.SHORT if side == TradeSide.LONG else TradeSide.LONG

            entry_price = 100.0 * (1 + random.uniform(-0.1, 0.1))
            pnl_pct = (
                random.uniform(-3, 5)
                if random.random() > (1 - self.config["win_rate"])
                else random.uniform(-3, 0)
            )

            trades.append(
                {
                    "trader": self.config["name"],
                    "persona": self.persona,
                    "symbol": symbol,
                    "side": side.value,
                    "entry_price": entry_price,
                    "pnl_pct": pnl_pct,
                    "timestamp": (now - timedelta(hours=i * 4)).isoformat(),
                }
            )

        return trades


def get_follow_signal(persona: str, symbol: str, market_data: Optional[dict] = None) -> dict | None:
    """Convenience function to get a follow signal.

    Args:
        persona: Social trading persona to follow.
        symbol: Trading symbol.
        market_data: Optional market context.

    Returns:
        Signal dict or None.
    """
    trader = SocialTrader(persona)
    return trader.get_signal(symbol, market_data)
