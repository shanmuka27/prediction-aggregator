# Prediction Market Aggregator

Pulls live market data from Polymarket's Gamma API and ranks markets by
recent trading activity.

Planned: store price snapshots over time to build historical charts,
detect significant moves, and compare odds against Kalshi.

## Setup

```
py -m venv venv
venv\Scripts\Activate.ps1
pip install requests
py fetch.py
```