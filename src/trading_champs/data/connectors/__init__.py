"""Exchange connectors for market data ingestion."""

from trading_champs.data.connectors.alpaca_connector import AlpacaConnector, AlpacaPaperConnector
from trading_champs.data.connectors.alpaca_market_data_connector import AlpacaMarketDataConnector
from trading_champs.data.connectors.base import BaseConnector
from trading_champs.data.connectors.ccxt_connector import CCXTConnector
from trading_champs.data.connectors.dry_run_connector import DryRunConnector
from trading_champs.data.connectors.yahoo_finance_connector import YahooFinanceConnector

# Renamed alias for clarity (AlpacaPaperConnector = AlpacaConnector(mode='paper'))
AlpacaPaperAPIConnector = AlpacaConnector

__all__ = [
    "AlpacaPaperConnector",
    "AlpacaPaperAPIConnector",
    "AlpacaMarketDataConnector",
    "BaseConnector",
    "CCXTConnector",
    "DryRunConnector",
    "YahooFinanceConnector",
]
