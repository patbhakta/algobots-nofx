

---




---



|------|------|
| **Commit Hash** | `e88f84215831d1682e05141eb0c27216dcbd6d47` |


|------|------|
| **Commit Hash** | `5af5c0b51773737f166eacea646e3960cee29f59` |


```

```

---



|------|----------|-----------|
| **NOFX** | `/api/equity-history-batch` | POST |
| **ChainOpera** | `/api/equity-history-batch` | POST |




```go
result["histories"] = histories
result["count"] = len(histories)
if len(errors) > 0 {
    result["errors"] = errors
}
```



```json
{
  "histories": {...},
  "errors": {},
  "count": 1
}
```


|------|-----------|------------|--------|
| `histories` | ✓ | ✓ | 100% |
| `errors` | ✓ | ✓ | 100% |
| `count` | ✓ | ✓ | 100% |



```go
history = append(history, map[string]interface{}{
    "timestamp":     snap.Timestamp,
    "total_equity":  snap.TotalEquity,
    "total_pnl":     snap.UnrealizedPnL,
    "total_pnl_pct": pnlPct,
    "balance":       snap.Balance,
})
```


```json
{
  "timestamp": "2025-12-15T11:21:05.432240",
  "balance": 227.30274403,
  "equity": 227.30274403,
  "total_pnl": 0
}
```


|----------------|-----------------|--------|
| `timestamp` | `timestamp` | 100% |
| `balance` | `balance` | 100% |
| `total_pnl` | `total_pnl` | 100% |




---




> "To 'modify' a work means to copy from or adapt all or part of the work in a fashion requiring copyright permission, other than the making of an exact copy."
>




> A "covered work" means either the unmodified Program or a work based on the Program.
>


> A "derivative work" is a work based upon one or more preexisting works, such as a translation... in which a work may be recast, transformed, or adapted.
>



|------|----------|


**Oracle v. Google (2021)**：



---



|---|------|-----------------|

---



```bash
git clone https://github.com/NoFxAiOS/nofx.git
cd nofx

git show e88f84215831d1682e05141eb0c27216dcbd6d47 --format="%H %ai %s" --no-patch

git show 5af5c0b51773737f166eacea646e3960cee29f59 --format="%H %ai %s" --no-patch

git show 5af5c0b51773737f166eacea646e3960cee29f59:api/server.go | grep -A 50 "handleEquityHistoryBatch"
```

---




> Notwithstanding any other provision of this License, if you modify the Program, your modified version must prominently offer all users interacting with it remotely through a computer network... an opportunity to receive the Corresponding Source of your version.




|--------|------|

---






|--------|------|------|




---


|---|----------|------|----------|

---








---



- **GitHub Issues**: https://github.com/NoFxAiOS/nofx/issues
- **Email**: contact@vergex.trade

---


---

