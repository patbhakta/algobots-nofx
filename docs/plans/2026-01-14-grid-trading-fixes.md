
> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.


**Architecture:**


---


|--------|------|------|

---



**Files:**
- Modify: `trader/interface.go:171-194`
- Modify: `trader/auto_trader_grid.go:324-409`



```go
// PlaceLimitOrder implements limit order using available methods
// For exchanges without native limit order support, this uses conditional orders
func (a *GridTraderAdapter) PlaceLimitOrder(req *LimitOrderRequest) (*LimitOrderResult, error) {
	// CRITICAL FIX: Set leverage before placing order
	if req.Leverage > 0 {
		if err := a.Trader.SetLeverage(req.Symbol, req.Leverage); err != nil {
			logger.Warnf("[Grid] Failed to set leverage %dx: %v", req.Leverage, err)
			// Continue anyway - some exchanges don't require explicit leverage setting
		}
	}

	// Use SetStopLoss/SetTakeProfit as conditional limit orders
	// For buy orders below current price, use stop-loss mechanism
	// For sell orders above current price, use take-profit mechanism
	var err error
	if req.Side == "BUY" {
		err = a.Trader.SetStopLoss(req.Symbol, "SHORT", req.Quantity, req.Price)
	} else {
		err = a.Trader.SetTakeProfit(req.Symbol, "LONG", req.Quantity, req.Price)
	}
	if err != nil {
		return nil, err
	}
	return &LimitOrderResult{
		OrderID:      req.ClientID,
		ClientID:     req.ClientID,
		Symbol:       req.Symbol,
		Side:         req.Side,
		PositionSide: req.PositionSide,
		Price:        req.Price,
		Quantity:     req.Quantity,
		Status:       "NEW",
	}, nil
}
```



```go
// InitializeGrid initializes the grid state and calculates levels
func (at *AutoTrader) InitializeGrid() error {

	at.gridState.IsInitialized = true

	// CRITICAL: Set leverage on exchange before trading
	if err := at.trader.SetLeverage(gridConfig.Symbol, gridConfig.Leverage); err != nil {
		logger.Warnf("[Grid] Failed to set leverage %dx on exchange: %v", gridConfig.Leverage, err)
		// Not fatal - continue with default leverage
	} else {
		logger.Infof("[Grid] Leverage set to %dx for %s", gridConfig.Leverage, gridConfig.Symbol)
	}

	logger.Infof("[Grid] Initialized: %d levels, $%.2f - $%.2f, spacing $%.2f",
		gridConfig.GridCount, at.gridState.LowerPrice, at.gridState.UpperPrice, at.gridState.GridSpacing)

	return nil
}
```


```bash
go build ./trader/
go test -v -run "TestLighter.*Leverage" ./trader/ -timeout 60s
```


```bash
git add trader/interface.go trader/auto_trader_grid.go
git commit -m "fix(grid): add leverage setting before order placement

CRITICAL BUG FIX:
- Call SetLeverage() in GridTraderAdapter.PlaceLimitOrder()
- Set leverage during grid initialization
- Log leverage setting results"
```

---



**Files:**
- Modify: `trader/interface.go:196-200`



```go
// CancelOrder cancels a specific order
func (a *GridTraderAdapter) CancelOrder(symbol, orderID string) error {
	// Try to use CancelOrder if trader supports it directly
	if canceler, ok := a.Trader.(interface {
		CancelOrder(symbol, orderID string) error
	}); ok {
		return canceler.CancelOrder(symbol, orderID)
	}

	// For traders that only support CancelAllOrders, log a warning
	// This is a limitation - we cannot cancel individual orders
	logger.Warnf("[Grid] Trader does not support individual order cancellation, " +
		"cannot cancel order %s. Consider using exchange-specific GridTrader implementation.", orderID)

	// Return error instead of canceling all orders
	return fmt.Errorf("individual order cancellation not supported for this exchange")
}
```


```go
import (
	"fmt"
)
```


```bash
go build ./trader/
```


```bash
git add trader/interface.go
git commit -m "fix(grid): prevent CancelOrder from canceling all orders

CRITICAL BUG FIX:
- CancelOrder no longer calls CancelAllOrders
- Try exchange-specific CancelOrder if available
- Return error if individual cancellation not supported"
```

---



**Files:**
- Modify: `trader/auto_trader_grid.go:324-409`



```go
// checkTotalPositionLimit checks if adding a new position would exceed total limits
// Returns: (allowed bool, currentPositionValue float64, maxAllowed float64)
func (at *AutoTrader) checkTotalPositionLimit(symbol string, additionalValue float64) (bool, float64, float64) {
	gridConfig := at.config.StrategyConfig.GridConfig

	// Calculate max allowed total position value
	// Total position should not exceed: TotalInvestment × Leverage
	maxTotalPositionValue := gridConfig.TotalInvestment * float64(gridConfig.Leverage)

	// Get current position value from exchange
	currentPositionValue := 0.0
	positions, err := at.trader.GetPositions()
	if err == nil {
		for _, pos := range positions {
			if sym, ok := pos["symbol"].(string); ok && sym == symbol {
				if size, ok := pos["positionAmt"].(float64); ok {
					if price, ok := pos["markPrice"].(float64); ok {
						currentPositionValue = math.Abs(size) * price
					} else if entryPrice, ok := pos["entryPrice"].(float64); ok {
						currentPositionValue = math.Abs(size) * entryPrice
					}
				}
			}
		}
	}

	// Also count pending orders as potential position
	at.gridState.mu.RLock()
	pendingValue := 0.0
	for _, level := range at.gridState.Levels {
		if level.State == "pending" {
			pendingValue += level.OrderQuantity * level.Price
		}
	}
	at.gridState.mu.RUnlock()

	totalAfterOrder := currentPositionValue + pendingValue + additionalValue
	allowed := totalAfterOrder <= maxTotalPositionValue

	return allowed, currentPositionValue + pendingValue, maxTotalPositionValue
}
```



```go
func (at *AutoTrader) placeGridLimitOrder(d *kernel.Decision, side string) error {

	// CRITICAL: Check total position limit before placing order
	orderValue := quantity * d.Price
	allowed, currentValue, maxValue := at.checkTotalPositionLimit(d.Symbol, orderValue)
	if !allowed {
		logger.Errorf("[Grid] TOTAL POSITION LIMIT EXCEEDED: current=$%.2f + order=$%.2f > max=$%.2f. Rejecting order.",
			currentValue, orderValue, maxValue)
		return fmt.Errorf("total position value $%.2f would exceed limit $%.2f", currentValue+orderValue, maxValue)
	}

	req := &LimitOrderRequest{
	}
}
```


```bash
go build ./trader/
```


```bash
git add trader/auto_trader_grid.go
git commit -m "fix(grid): add total position value limit check

CRITICAL: Prevent excessive position accumulation
- New checkTotalPositionLimit() function
- Checks current + pending + new order value
- Rejects orders that would exceed TotalInvestment × Leverage
- Logs clear error messages when limit exceeded"
```

---



**Files:**



```go
// checkAndExecuteStopLoss checks if any filled level has exceeded stop loss and closes it
func (at *AutoTrader) checkAndExecuteStopLoss() {
	gridConfig := at.config.StrategyConfig.GridConfig
	if gridConfig.StopLossPct <= 0 {
		return // Stop loss not configured
	}

	currentPrice, err := at.trader.GetMarketPrice(gridConfig.Symbol)
	if err != nil {
		logger.Warnf("[Grid] Failed to get market price for stop loss check: %v", err)
		return
	}

	at.gridState.mu.Lock()
	defer at.gridState.mu.Unlock()

	for i := range at.gridState.Levels {
		level := &at.gridState.Levels[i]
		if level.State != "filled" || level.PositionEntry <= 0 {
			continue
		}

		// Calculate loss percentage
		var lossPct float64
		if level.Side == "buy" {
			// Long position: loss when price drops
			lossPct = (level.PositionEntry - currentPrice) / level.PositionEntry * 100
		} else {
			// Short position: loss when price rises
			lossPct = (currentPrice - level.PositionEntry) / level.PositionEntry * 100
		}

		// Check if stop loss triggered
		if lossPct >= gridConfig.StopLossPct {
			logger.Warnf("[Grid] STOP LOSS TRIGGERED: Level %d, entry=$%.2f, current=$%.2f, loss=%.2f%%",
				i, level.PositionEntry, currentPrice, lossPct)

			// Close the position
			var closeErr error
			if level.Side == "buy" {
				_, closeErr = at.trader.CloseLong(gridConfig.Symbol, level.PositionSize)
			} else {
				_, closeErr = at.trader.CloseShort(gridConfig.Symbol, level.PositionSize)
			}

			if closeErr != nil {
				logger.Errorf("[Grid] Failed to execute stop loss for level %d: %v", i, closeErr)
			} else {
				level.State = "stopped"
				level.UnrealizedPnL = -lossPct * level.AllocatedUSD / 100
				at.gridState.TotalTrades++
				logger.Infof("[Grid] Stop loss executed: Level %d closed at $%.2f (loss %.2f%%)",
					i, currentPrice, lossPct)
			}
		}
	}
}
```



```go
func (at *AutoTrader) syncGridState() {

	logger.Debugf("[Grid] Synced state: position=%.4f, orders=%d", totalPosition, len(openOrders))

	// CRITICAL: Check stop loss for filled levels
	at.checkAndExecuteStopLoss()
}
```


```bash
go build ./trader/
```


```bash
git add trader/auto_trader_grid.go
git commit -m "feat(grid): implement stop loss execution

CRITICAL: Add code-level stop loss protection
- New checkAndExecuteStopLoss() function
- Checks each filled level against StopLossPct
- Automatically closes positions exceeding stop loss
- Called during every grid state sync"
```

---



**Files:**



```go
// BreakoutType represents the type of price breakout
type BreakoutType string

const (
	BreakoutNone  BreakoutType = "none"
	BreakoutUpper BreakoutType = "upper"
	BreakoutLower BreakoutType = "lower"
)

// checkBreakout detects if price has broken out of grid range
// Returns breakout type and percentage beyond boundary
func (at *AutoTrader) checkBreakout() (BreakoutType, float64) {
	gridConfig := at.config.StrategyConfig.GridConfig

	currentPrice, err := at.trader.GetMarketPrice(gridConfig.Symbol)
	if err != nil {
		return BreakoutNone, 0
	}

	at.gridState.mu.RLock()
	upper := at.gridState.UpperPrice
	lower := at.gridState.LowerPrice
	at.gridState.mu.RUnlock()

	if upper <= 0 || lower <= 0 {
		return BreakoutNone, 0
	}

	// Check upper breakout
	if currentPrice > upper {
		breakoutPct := (currentPrice - upper) / upper * 100
		return BreakoutUpper, breakoutPct
	}

	// Check lower breakout
	if currentPrice < lower {
		breakoutPct := (lower - currentPrice) / lower * 100
		return BreakoutLower, breakoutPct
	}

	return BreakoutNone, 0
}

// handleBreakout handles price breakout from grid range
func (at *AutoTrader) handleBreakout(breakoutType BreakoutType, breakoutPct float64) error {
	gridConfig := at.config.StrategyConfig.GridConfig

	logger.Warnf("[Grid] BREAKOUT DETECTED: %s, %.2f%% beyond boundary", breakoutType, breakoutPct)

	// If breakout exceeds 2%, pause grid and cancel orders
	if breakoutPct >= 2.0 {
		logger.Warnf("[Grid] Significant breakout (%.2f%%), pausing grid and canceling orders", breakoutPct)

		// Cancel all pending orders to prevent further losses
		if err := at.cancelAllGridOrders(); err != nil {
			logger.Errorf("[Grid] Failed to cancel orders on breakout: %v", err)
		}

		// Pause grid trading
		at.gridState.mu.Lock()
		at.gridState.IsPaused = true
		at.gridState.mu.Unlock()

		return fmt.Errorf("grid paused due to %s breakout (%.2f%%)", breakoutType, breakoutPct)
	}

	// If breakout is minor (< 2%), consider adjusting grid
	if breakoutPct >= 1.0 {
		logger.Infof("[Grid] Minor breakout (%.2f%%), considering grid adjustment", breakoutPct)
		// Let AI decide whether to adjust
	}

	return nil
}
```



```go
func (at *AutoTrader) RunGridCycle() error {
	if at.gridState == nil || !at.gridState.IsInitialized {
		if err := at.InitializeGrid(); err != nil {
			return fmt.Errorf("failed to initialize grid: %w", err)
		}
	}

	// CRITICAL: Check for breakout before executing any trades
	breakoutType, breakoutPct := at.checkBreakout()
	if breakoutType != BreakoutNone {
		if err := at.handleBreakout(breakoutType, breakoutPct); err != nil {
			return err // Grid paused due to breakout
		}
	}

	// Check if grid is paused
	at.gridState.mu.RLock()
	isPaused := at.gridState.IsPaused
	at.gridState.mu.RUnlock()
	if isPaused {
		logger.Infof("[Grid] Grid is paused, skipping cycle")
		return nil
	}

	gridConfig := at.config.StrategyConfig.GridConfig
}
```


```bash
go build ./trader/
```


```bash
git add trader/auto_trader_grid.go
git commit -m "feat(grid): add breakout detection and auto-pause

CRITICAL: Detect price breakout from grid range
- New checkBreakout() function
- Auto-pause grid on significant breakout (>2%)
- Cancel all orders when breakout detected
- Prevent continued losses in trending market"
```

---



**Files:**



```go
// checkMaxDrawdown checks if current drawdown exceeds maximum allowed
// Returns: (exceeded bool, currentDrawdown float64)
func (at *AutoTrader) checkMaxDrawdown() (bool, float64) {
	gridConfig := at.config.StrategyConfig.GridConfig
	if gridConfig.MaxDrawdownPct <= 0 {
		return false, 0
	}

	// Get current equity
	balance, err := at.trader.GetBalance()
	if err != nil {
		return false, 0
	}

	currentEquity := 0.0
	if equity, ok := balance["total_equity"].(float64); ok {
		currentEquity = equity
	} else if total, ok := balance["totalWalletBalance"].(float64); ok {
		if unrealized, ok := balance["totalUnrealizedProfit"].(float64); ok {
			currentEquity = total + unrealized
		}
	}

	if currentEquity <= 0 {
		return false, 0
	}

	// Update peak equity
	at.gridState.mu.Lock()
	if currentEquity > at.gridState.PeakEquity {
		at.gridState.PeakEquity = currentEquity
	}
	peakEquity := at.gridState.PeakEquity
	at.gridState.mu.Unlock()

	if peakEquity <= 0 {
		return false, 0
	}

	// Calculate current drawdown
	drawdown := (peakEquity - currentEquity) / peakEquity * 100

	// Update max drawdown tracking
	at.gridState.mu.Lock()
	if drawdown > at.gridState.MaxDrawdown {
		at.gridState.MaxDrawdown = drawdown
	}
	at.gridState.mu.Unlock()

	return drawdown >= gridConfig.MaxDrawdownPct, drawdown
}

// emergencyExit closes all positions and cancels all orders
func (at *AutoTrader) emergencyExit(reason string) error {
	gridConfig := at.config.StrategyConfig.GridConfig

	logger.Errorf("[Grid] EMERGENCY EXIT: %s", reason)

	// Cancel all orders
	if err := at.cancelAllGridOrders(); err != nil {
		logger.Errorf("[Grid] Failed to cancel orders in emergency: %v", err)
	}

	// Close all positions
	positions, err := at.trader.GetPositions()
	if err == nil {
		for _, pos := range positions {
			if sym, ok := pos["symbol"].(string); ok && sym == gridConfig.Symbol {
				if size, ok := pos["positionAmt"].(float64); ok && size != 0 {
					if size > 0 {
						at.trader.CloseLong(gridConfig.Symbol, size)
					} else {
						at.trader.CloseShort(gridConfig.Symbol, -size)
					}
				}
			}
		}
	}

	// Pause grid
	at.gridState.mu.Lock()
	at.gridState.IsPaused = true
	at.gridState.mu.Unlock()

	return nil
}
```



```go
func (at *AutoTrader) RunGridCycle() error {

	// CRITICAL: Check for breakout

	// CRITICAL: Check max drawdown
	exceeded, drawdown := at.checkMaxDrawdown()
	if exceeded {
		return at.emergencyExit(fmt.Sprintf("max drawdown exceeded: %.2f%%", drawdown))
	}

}
```


```bash
go build ./trader/
```


```bash
git add trader/auto_trader_grid.go
git commit -m "feat(grid): enforce max drawdown limit with emergency exit

CRITICAL: Add drawdown protection
- New checkMaxDrawdown() function tracks peak equity
- emergencyExit() closes all positions and cancels orders
- Auto-pause grid when MaxDrawdownPct exceeded
- Protect capital from excessive losses"
```

---



**Files:**



```go
// checkDailyLossLimit checks if daily loss exceeds limit
// Returns: (exceeded bool, dailyLossPct float64)
func (at *AutoTrader) checkDailyLossLimit() (bool, float64) {
	gridConfig := at.config.StrategyConfig.GridConfig
	if gridConfig.DailyLossLimitPct <= 0 {
		return false, 0
	}

	at.gridState.mu.Lock()
	// Reset daily PnL if new day
	now := time.Now()
	if now.YearDay() != at.gridState.LastDailyReset.YearDay() ||
	   now.Year() != at.gridState.LastDailyReset.Year() {
		at.gridState.DailyPnL = 0
		at.gridState.LastDailyReset = now
	}
	dailyPnL := at.gridState.DailyPnL
	at.gridState.mu.Unlock()

	// Calculate daily loss as percentage of total investment
	dailyLossPct := 0.0
	if gridConfig.TotalInvestment > 0 && dailyPnL < 0 {
		dailyLossPct = (-dailyPnL) / gridConfig.TotalInvestment * 100
	}

	return dailyLossPct >= gridConfig.DailyLossLimitPct, dailyLossPct
}

// updateDailyPnL updates the daily PnL tracking
func (at *AutoTrader) updateDailyPnL(realizedPnL float64) {
	at.gridState.mu.Lock()
	at.gridState.DailyPnL += realizedPnL
	at.gridState.TotalProfit += realizedPnL
	at.gridState.mu.Unlock()
}
```



```go
func (at *AutoTrader) RunGridCycle() error {

	// CRITICAL: Check max drawdown
	// ...

	// CRITICAL: Check daily loss limit
	exceeded, dailyLossPct := at.checkDailyLossLimit()
	if exceeded {
		logger.Errorf("[Grid] Daily loss limit exceeded: %.2f%%", dailyLossPct)
		at.gridState.mu.Lock()
		at.gridState.IsPaused = true
		at.gridState.mu.Unlock()
		return fmt.Errorf("daily loss limit exceeded: %.2f%%", dailyLossPct)
	}

}
```


```bash
go build ./trader/
```


```bash
git add trader/auto_trader_grid.go
git commit -m "feat(grid): enforce daily loss limit

- New checkDailyLossLimit() function
- Track daily PnL with auto-reset at midnight
- Pause grid when DailyLossLimitPct exceeded
- Prevent excessive single-day losses"
```

---



**Files:**



```go
// checkGridSkew checks if grid is heavily skewed (too many fills on one side)
// Returns: (skewed bool, buyFilledCount int, sellFilledCount int)
func (at *AutoTrader) checkGridSkew() (bool, int, int) {
	at.gridState.mu.RLock()
	defer at.gridState.mu.RUnlock()

	buyFilled := 0
	sellFilled := 0
	buyEmpty := 0
	sellEmpty := 0

	for _, level := range at.gridState.Levels {
		if level.Side == "buy" {
			if level.State == "filled" {
				buyFilled++
			} else if level.State == "empty" {
				buyEmpty++
			}
		} else {
			if level.State == "filled" {
				sellFilled++
			} else if level.State == "empty" {
				sellEmpty++
			}
		}
	}

	// Grid is skewed if one side has 3x more fills than the other
	// or if one side is completely empty
	skewed := false
	if buyFilled > 0 && sellFilled == 0 && sellEmpty > 5 {
		skewed = true // All buys filled, no sells
	} else if sellFilled > 0 && buyFilled == 0 && buyEmpty > 5 {
		skewed = true // All sells filled, no buys
	} else if buyFilled >= 3*sellFilled && buyFilled > 5 {
		skewed = true
	} else if sellFilled >= 3*buyFilled && sellFilled > 5 {
		skewed = true
	}

	return skewed, buyFilled, sellFilled
}

// autoAdjustGrid automatically adjusts grid when heavily skewed
func (at *AutoTrader) autoAdjustGrid() {
	skewed, buyFilled, sellFilled := at.checkGridSkew()
	if !skewed {
		return
	}

	logger.Warnf("[Grid] Grid heavily skewed: buy_filled=%d, sell_filled=%d. Auto-adjusting...",
		buyFilled, sellFilled)

	gridConfig := at.config.StrategyConfig.GridConfig

	// Get current price
	currentPrice, err := at.trader.GetMarketPrice(gridConfig.Symbol)
	if err != nil {
		logger.Errorf("[Grid] Failed to get price for auto-adjust: %v", err)
		return
	}

	// Check if price is near grid boundary
	at.gridState.mu.RLock()
	upper := at.gridState.UpperPrice
	lower := at.gridState.LowerPrice
	at.gridState.mu.RUnlock()

	// Only adjust if price has moved significantly (>50% of grid range)
	gridRange := upper - lower
	midPrice := (upper + lower) / 2
	priceDeviation := math.Abs(currentPrice - midPrice)

	if priceDeviation < gridRange*0.3 {
		return // Price still near center, don't adjust
	}

	// Cancel existing orders and reinitialize
	logger.Infof("[Grid] Adjusting grid around new price $%.2f", currentPrice)
	at.cancelAllGridOrders()
	at.initializeGridLevels(currentPrice, gridConfig)
}
```



```go
func (at *AutoTrader) syncGridState() {

	// Check stop loss
	at.checkAndExecuteStopLoss()

	// Check grid skew and auto-adjust if needed
	at.autoAdjustGrid()
}
```


```bash
go build ./trader/
```


```bash
git add trader/auto_trader_grid.go
git commit -m "feat(grid): add automatic grid adjustment

- New checkGridSkew() detects imbalanced grid
- autoAdjustGrid() reinitializes around current price
- Prevents grid from becoming ineffective after drift
- Triggers when one side is 3x more filled than other"
```

---



**Files:**
- Modify: `trader/auto_trader_grid.go:504-565`



```go
// syncGridState syncs grid state with exchange
func (at *AutoTrader) syncGridState() {
	gridConfig := at.config.StrategyConfig.GridConfig

	// Get open orders from exchange
	openOrders, err := at.trader.GetOpenOrders(gridConfig.Symbol)
	if err != nil {
		logger.Warnf("[Grid] Failed to get open orders: %v", err)
		return
	}

	// Build set of active order IDs
	activeOrderIDs := make(map[string]bool)
	for _, order := range openOrders {
		activeOrderIDs[order.OrderID] = true
	}

	// Get current positions to verify fills
	positions, err := at.trader.GetPositions()
	currentPositionSize := 0.0
	if err == nil {
		for _, pos := range positions {
			if sym, ok := pos["symbol"].(string); ok && sym == gridConfig.Symbol {
				if size, ok := pos["positionAmt"].(float64); ok {
					currentPositionSize = size
				}
			}
		}
	}

	// Update levels based on order status
	at.gridState.mu.Lock()
	previousFilledCount := 0
	for _, level := range at.gridState.Levels {
		if level.State == "filled" {
			previousFilledCount++
		}
	}

	for i := range at.gridState.Levels {
		level := &at.gridState.Levels[i]
		if level.State == "pending" && level.OrderID != "" {
			if !activeOrderIDs[level.OrderID] {
				// Order no longer exists - check if position changed to determine fill vs cancel
				// This is a heuristic - ideally we'd query order history
				if math.Abs(currentPositionSize) > math.Abs(float64(previousFilledCount)*level.OrderQuantity) {
					// Position increased, likely filled
					level.State = "filled"
					level.PositionEntry = level.Price
					level.PositionSize = level.OrderQuantity
					at.gridState.TotalTrades++
					logger.Infof("[Grid] Level %d order filled at $%.2f", i, level.Price)
				} else {
					// Position didn't increase as expected, likely cancelled
					level.State = "empty"
					level.OrderID = ""
					level.OrderQuantity = 0
					logger.Infof("[Grid] Level %d order cancelled/expired", i)
				}
				delete(at.gridState.OrderBook, level.OrderID)
			}
		}
	}
	at.gridState.mu.Unlock()

	logger.Debugf("[Grid] Synced state: position=%.4f, orders=%d", currentPositionSize, len(openOrders))

	// Check stop loss
	at.checkAndExecuteStopLoss()

	// Check grid skew
	at.autoAdjustGrid()
}
```


```bash
go build ./trader/
```


```bash
git add trader/auto_trader_grid.go
git commit -m "fix(grid): improve order state sync logic

- Don't assume missing orders are filled
- Compare position size to determine fill vs cancel
- Properly reset cancelled orders to empty state
- More accurate grid state tracking"
```

---



```bash
go build ./...

go test -v ./trader/... -timeout 300s

go test -v -run "Grid" ./trader/ -timeout 60s
```



---


```

┌─────────────┐     ┌─────────────┐     ┌─────────────────────────┐     ┌─────────────┐
└─────────────┘     └─────────────┘     └─────────────────────────┘     └─────────────┘
                                                    │
                                                    ▼
                    ┌────────────────────────────────────────────────────┐
                    └────────────────────────────────────────────────────┘
```
