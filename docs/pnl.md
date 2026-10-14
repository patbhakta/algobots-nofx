





```
Initial Balance = Total Wallet Balance + Total Unrealized Profit
```

---



```
Total Equity = Total Wallet Balance + Total Unrealized Profit
```



---



```
Total PNL = Current Equity - Initial Balance
Total PNL % = (Total PNL / Initial Balance) × 100%
```

```
-----------------------------------
Total PNL:       +1,500 USDT
Total PNL %:     +15%
```





```
Position PNL % = (Unrealized PnL / Margin Used) × 100%
```


---



|-----|------|

---




```go
balanceInfo, _ := tempTrader.GetBalance()

totalWalletBalance := balanceInfo["totalWalletBalance"].(float64)
totalUnrealizedProfit := balanceInfo["totalUnrealizedProfit"].(float64)

initialEquity := totalWalletBalance + totalUnrealizedProfit

trader := &config.TraderRecord{
}
```

---





---





---





```json
{
  "initial_balance": 10000.0
}
```

```
```


---


```
┌─────────────────────────────────────────┐
│    → initial_balance = Total Equity     │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│      total_pnl = current - initial      │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
└─────────────────────────────────────────┘
```

---


|-----|------|---------|---------|---------|

---


```
```

```
```

```
```

```
```

```
```

---



---



  ```
  ```



---


|-----|------|----------|

---


