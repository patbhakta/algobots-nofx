package nautilus

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"time"

	"nofx/gateway"
	"nofx/trader/types"
)

var errUnsupported = errors.New("operation is not exposed by the Nautilus gateway contract")

// Trader routes NoFX exchange operations through the generated gateway client.
// AccountID is the gateway account identifier; it is never an exchange secret.
type Trader struct {
	client    *gateway.Client
	accountID string
}

func NewTrader(baseURL, bearer, accountID string) *Trader {
	return &Trader{client: gateway.NewClient(baseURL, bearer), accountID: accountID}
}

func NewTraderWithClient(client *gateway.Client, accountID string) *Trader {
	return &Trader{client: client, accountID: accountID}
}

func (t *Trader) GetBalance() (map[string]interface{}, error) {
	accounts, err := t.client.ListAccounts(context.Background())
	if err != nil {
		return nil, err
	}
	for _, account := range accounts {
		if account.AccountID != t.accountID {
			continue
		}
		if account.Mode != gateway.ModePaper {
			return nil, fmt.Errorf("nautilus account %q is not PAPER", t.accountID)
		}
		if len(account.Balances) == 0 {
			return nil, fmt.Errorf("nautilus account %q has no balances", t.accountID)
		}
		balance := account.Balances[0]
		for _, candidate := range account.Balances {
			if candidate.Currency == "USDT" || candidate.Currency == "USD" {
				balance = candidate
				break
			}
		}
		return map[string]interface{}{
			"total_equity": string(balance.Total), "available_balance": string(balance.Free), "asset": balance.Currency,
		}, nil
	}
	return nil, fmt.Errorf("nautilus account %q not found", t.accountID)
}

func (t *Trader) GetPositions() ([]map[string]interface{}, error) { return nil, errUnsupported }
func (t *Trader) submitMarket(symbol string, quantity float64, side gateway.Side, reduceOnly bool) (map[string]interface{}, error) {
	qty := gateway.Decimal(strconv.FormatFloat(quantity, 'f', -1, 64))
	key := fmt.Sprintf("nofx-%s-%d", t.accountID, time.Now().UnixNano())
	order, err := t.client.SubmitOrder(context.Background(), key, gateway.OrderRequest{
		AccountID: t.accountID, Symbol: symbol, Side: side, Qty: qty,
		OrderType: gateway.OrderType("MARKET"), ReduceOnly: reduceOnly,
	})
	if err != nil {
		return nil, err
	}
	return map[string]interface{}{"order_id": order.ClientOrderID, "status": order.Status}, nil
}

func (t *Trader) OpenLong(symbol string, quantity float64, _ int) (map[string]interface{}, error) {
	return t.submitMarket(symbol, quantity, gateway.Side("BUY"), false)
}
func (t *Trader) OpenShort(symbol string, quantity float64, _ int) (map[string]interface{}, error) {
	return t.submitMarket(symbol, quantity, gateway.Side("SELL"), false)
}
func (t *Trader) CloseLong(symbol string, quantity float64) (map[string]interface{}, error) {
	return t.submitMarket(symbol, quantity, gateway.Side("SELL"), true)
}
func (t *Trader) CloseShort(symbol string, quantity float64) (map[string]interface{}, error) {
	return t.submitMarket(symbol, quantity, gateway.Side("BUY"), true)
}
func (t *Trader) SetLeverage(string, int) error { return errUnsupported }
func (t *Trader) SetMarginMode(string, bool) error { return errUnsupported }
func (t *Trader) GetMarketPrice(string) (float64, error) { return 0, errUnsupported }
func (t *Trader) SetStopLoss(string, string, float64, float64) error { return errUnsupported }
func (t *Trader) SetTakeProfit(string, string, float64, float64) error { return errUnsupported }
func (t *Trader) CancelStopLossOrders(string) error { return errUnsupported }
func (t *Trader) CancelTakeProfitOrders(string) error { return errUnsupported }
func (t *Trader) CancelAllOrders(string) error { return errUnsupported }
func (t *Trader) CancelStopOrders(string) error { return errUnsupported }
func (t *Trader) FormatQuantity(_ string, quantity float64) (string, error) {
	return fmt.Sprint(quantity), nil
}
func (t *Trader) GetOrderStatus(string, string) (map[string]interface{}, error) { return nil, errUnsupported }
func (t *Trader) GetClosedPnL(time.Time, int) ([]types.ClosedPnLRecord, error) { return nil, errUnsupported }
func (t *Trader) GetOpenOrders(string) ([]types.OpenOrder, error) { return nil, errUnsupported }

var _ types.Trader = (*Trader)(nil)
