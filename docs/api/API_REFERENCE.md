

- **Base URL**: `https://nofxos.ai`


```
GET /api/ai500/list?auth=your_api_key
```

```
GET /api/ai500/list
Authorization: Bearer your_api_key
```


```json
{
  "success": true,
  "data": { ... }
}
```

```json
{
  "success": false,
}
```

---




|--------|------|------|------|


|--------|------|------|


|--------|------|------|

---



|--------|------|------|

---





```
GET /api/ai500/list
```


```json
{
  "success": true,
  "data": {
    "count": 5,
    "coins": [
      {
        "pair": "BTCUSDT",
        "score": 85.234,
        "start_time": 1704067200,
        "start_price": 42000.5,
        "last_score": 83.5,
        "max_score": 87.2,
        "max_price": 45000.0,
        "increase_percent": 7.14
      }
    ]
  }
}
```

|------|------|------|

---


```
GET /api/ai500/:symbol
```

|------|------|------|------|

```
GET /api/ai500/BTC
GET /api/ai500/ETHUSDT
```

```json
{
  "success": true,
  "data": {
    "info": {
      "pair": "BTCUSDT",
      "score": 85.234,
      "start_time": 1704067200,
      "start_price": 42000.5,
      "last_score": 83.5,
      "max_score": 87.2,
      "max_price": 45000.0,
      "increase_percent": 7.14
    },
    "current_price": 44500.0,
    "score": 85.234
  }
}
```

---



```
GET /api/ai500/stats
```

```json
{
  "success": true,
  "data": {
    "statistics": {
      "total_count": 50,
      "average_score": 72.5,
      "max_score": 95.2,
      "min_score": 55.3,
      "average_increase": 12.5
    },
    "top_coins": [...],
    "bottom_coins": [...]
  }
}
```

---





```
GET /api/oi/top-ranking
```

|------|------|--------|------|

```
GET /api/oi/top-ranking?limit=50&duration=4h
```

```json
{
  "success": true,
  "data": {
    "count": 20,
    "exchange": "binance",
    "time_range_param": "4h",
    "rank_type": "top",
    "limit": 50,
    "positions": [
      {
        "rank": 1,
        "symbol": "BTCUSDT",
        "price": 44500.0,
        "oi_delta": 1500.5,
        "oi_delta_value": 65000000,
        "oi_delta_percent": 2.5,
        "current_oi": 62000,
        "price_delta_percent": 1.2,
        "net_long": 35000,
        "net_short": 27000
      }
    ]
  }
}
```

|------|------|------|------|

---



```
GET /api/oi/low-ranking
```


```
GET /api/oi/low-ranking?limit=30&duration=24h
```

---


```
GET /api/oi/top
```


---




```
GET /api/netflow/top-ranking
```

|------|------|--------|------|

```
GET /api/netflow/top-ranking?limit=30&duration=4h&type=institution&trade=future
```

```json
{
  "success": true,
  "data": {
    "count": 30,
    "type": "institution",
    "time_range": "4h",
    "rank_type": "top",
    "limit": 30,
    "netflows": [
      {
        "rank": 1,
        "symbol": "BTCUSDT",
        "amount": 15000000.5,
        "price": 44500.0
      }
    ]
  }
}
```

|------|------|------|------|

---


```
GET /api/netflow/low-ranking
```


```
GET /api/netflow/low-ranking?limit=20&duration=1h&type=personal&trade=spot
```

---


```
GET /api/netflow/top
```


---




```
GET /api/price/ranking
```

|------|------|--------|------|

```
GET /api/price/ranking?duration=1h,4h,24h&limit=20
```

```json
{
  "success": true,
  "data": {
    "durations": ["1h", "4h", "24h"],
    "limit": 20,
    "data": {
      "1h": {
        "top": [
          {
            "pair": "MOGUSDT",
            "symbol": "MOG",
            "price_delta": 0.0723,
            "price": 0.00123,
            "future_flow": 201500,
            "spot_flow": 0,
            "oi": 15000000,
            "oi_delta": 500000,
            "oi_delta_value": 615
          }
        ],
        "low": [
          {
            "pair": "XYZUSDT",
            "symbol": "XYZ",
            "price_delta": -0.0512,
            "price": 1.234,
            "future_flow": -50000,
            "spot_flow": -10000,
            "oi": 8000000,
            "oi_delta": -200000,
            "oi_delta_value": -246800
          }
        ]
      },
      "4h": { ... },
      "24h": { ... }
    }
  }
}
```

|------|------|------|------|


---




```
GET /api/coin/:symbol
```

|------|------|------|------|

|------|------|--------|------|

|------|------|

```
GET /api/coin/BTC?include=netflow,oi,price,ai500
GET /api/coin/ETHUSDT?include=netflow,oi
```

```json
{
  "success": true,
  "data": {
    "symbol": "BTCUSDT",
    "price": 44500.0,
    "ai500": {
      "score": 85.234,
      "is_active": true,
      "start_time": 1704067200,
      "start_price": 42000.5,
      "increase_percent": 5.95
    },
    "netflow": {
      "institution": {
        "future": {
          "1m": 50000,
          "5m": 200000,
          "15m": 500000,
          "30m": 800000,
          "1h": 1500000,
          "4h": 5000000,
          "8h": 8000000,
          "12h": 10000000,
          "24h": 15000000,
          "2d": 25000000,
          "3d": 35000000,
          "5d": 50000000,
          "7d": 75000000
        },
        "spot": { ... }
      },
      "personal": {
        "future": { ... },
        "spot": { ... }
      }
    },
    "oi": {
      "binance": {
        "current_oi": 62000,
        "net_long": 35000,
        "net_short": 27000,
        "delta": {
          "1m": {
            "oi_delta": 50,
            "oi_delta_value": 2225000,
            "oi_delta_percent": 0.08
          },
          "5m": { ... },
          "1h": { ... },
          "4h": { ... },
          "24h": { ... }
        }
      },
      "bybit": { ... }
    },
    "price_change": {
      "1m": 0.001,
      "5m": 0.005,
      "15m": 0.008,
      "30m": 0.012,
      "1h": 0.015,
      "4h": 0.025,
      "8h": 0.035,
      "12h": 0.042,
      "24h": 0.055,
      "2d": 0.08,
      "3d": 0.12,
      "5d": 0.18,
      "7d": 0.25
    }
  }
}
```


|------|------|------|------|

|------|------|------|------|

|------|------|------|------|

|------|------|------|------|

---


|------------|------|----------|

```json
{
  "success": false,
  "error": "unauthorized"
}
```

---



```bash
curl "https://nofxos.ai/api/ai500/list?auth=your_api_key"

curl "https://nofxos.ai/api/ai500/list" \
  -H "Authorization: Bearer your_api_key"

curl "https://nofxos.ai/api/price/ranking?duration=1h&limit=20&auth=your_api_key"

curl "https://nofxos.ai/api/price/ranking?duration=1h,4h,24h&limit=10&auth=your_api_key"

curl "https://nofxos.ai/api/coin/BTC?auth=your_api_key"

curl "https://nofxos.ai/api/coin/BTC?include=netflow,oi&auth=your_api_key"

curl "https://nofxos.ai/api/oi/top-ranking?duration=4h&limit=50&auth=your_api_key"

curl "https://nofxos.ai/api/oi/low-ranking?duration=24h&limit=30&auth=your_api_key"

curl "https://nofxos.ai/api/netflow/top-ranking?type=institution&trade=future&duration=1h&auth=your_api_key"

curl "https://nofxos.ai/api/netflow/low-ranking?type=personal&trade=spot&duration=4h&auth=your_api_key"
```


```python
import requests

BASE_URL = "https://nofxos.ai"
API_KEY = "your_api_key"

def get_with_query_auth(endpoint, params=None):
    if params is None:
        params = {}
    params["auth"] = API_KEY
    response = requests.get(f"{BASE_URL}{endpoint}", params=params)
    return response.json()

def get_with_header_auth(endpoint, params=None):
    headers = {"Authorization": f"Bearer {API_KEY}"}
    response = requests.get(f"{BASE_URL}{endpoint}", params=params, headers=headers)
    return response.json()

def get_ai500_list():
    return get_with_query_auth("/api/ai500/list")

def get_price_ranking(durations="1h,4h,24h", limit=20):
    return get_with_query_auth("/api/price/ranking", {
        "duration": durations,
        "limit": limit
    })

def get_coin_stats(symbol, include="netflow,oi,price,ai500"):
    return get_with_query_auth(f"/api/coin/{symbol}", {
        "include": include
    })

def get_oi_ranking(rank_type="top", duration="1h", limit=20):
    endpoint = f"/api/oi/{rank_type}-ranking"
    return get_with_query_auth(endpoint, {
        "duration": duration,
        "limit": limit
    })

def get_netflow_ranking(rank_type="top", duration="1h", limit=20,
                        flow_type="institution", trade="future"):
    endpoint = f"/api/netflow/{rank_type}-ranking"
    return get_with_query_auth(endpoint, {
        "duration": duration,
        "limit": limit,
        "type": flow_type,
        "trade": trade
    })

if __name__ == "__main__":
    ai500 = get_ai500_list()

    ranking = get_price_ranking("1h", 10)
    for coin in ranking['data']['data']['1h']['top'][:3]:
        pct = coin['price_delta'] * 100
        print(f"{coin['symbol']}: {pct:.2f}%")

    btc = get_coin_stats("BTC")

    oi = get_oi_ranking("top", "4h", 20)
    for pos in oi['data']['positions'][:3]:
```


```typescript
const BASE_URL = "https://nofxos.ai";
const API_KEY = "your_api_key";

async function apiRequest<T>(endpoint: string, params: Record<string, any> = {}): Promise<T> {
    const url = new URL(`${BASE_URL}${endpoint}`);
    params.auth = API_KEY;
    Object.entries(params).forEach(([key, value]) => {
        url.searchParams.append(key, String(value));
    });

    const response = await fetch(url.toString());
    return response.json();
}

interface PriceRankingItem {
    pair: string;
    symbol: string;
    price: number;
    future_flow: number;
    spot_flow: number;
}

async function getPriceRanking(durations = "1h", limit = 20) {
    const data = await apiRequest<any>("/api/price/ranking", { duration: durations, limit });
    return data;
}

async function main() {
    const ranking = await getPriceRanking("1h,4h", 10);

    for (const coin of ranking.data.data["1h"].top) {
        const pctChange = (coin.price_delta * 100).toFixed(2);
        console.log(`${coin.symbol}: ${pctChange}%`);
    }
}
```

---












