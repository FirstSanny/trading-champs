# Trading Champs

Automated trading system for generating stable income through algorithmic trading.

## Project Structure

```
trading_champs/
├── src/              # Source code
├── tests/            # Test files
├── config/           # Configuration files
├── scripts/          # Utility scripts
├── docs/             # Documentation
└── .gitlab-ci.yml     # CI/CD pipelines
```

## Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install in development mode
pip install -e ".[dev]"
```

## Development

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Type checking
mypy src/

# Formatting
black src/ tests/
isort src/ tests/
```

## Deployment

See [docs/deployment.md](docs/deployment.md) for deployment instructions.