#!/usr/bin/env python3
"""Run the P&L Dashboard web server."""

import uvicorn
from trading_champs.web.app import create_app


def main():
    """Run the dashboard server."""
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
