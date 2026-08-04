# AlgoBots

Automated stock technical analysis bot orchestrated by Kestra.

## What It Does

- Fetches OHLCV data via yfinance (free, no API key)
- Calculates RSI, MACD, Bollinger Bands, SMA/EMA, volume analysis
- Generates formatted technical analysis reports
- Scheduled daily via Kestra

## Pipeline

```
Kestra Flow: algobots.daily-analysis
├── fetch_data.py        → Download OHLCV from yfinance
├── calculate_indicators.py → RSI, MACD, Bollinger, SMA/EMA
├── generate_report.py   → Format analysis into markdown report
└── deliver.py           → Save report + notification
```

## Quick Start

```bash
pip install -e ".[dev]"
pytest -v
```

## Company Pipeline

This project was built using the LettuceAI agent company pipeline:
1. CEO (J.A.R.V.I.S.) wrote vision brief
2. R&D designed architecture (Paperclip BHAA-1347)
3. CEO reviewed and approved
4. Tech Lead implemented
5. CEO code reviewed
6. Deployed to Kestra production
