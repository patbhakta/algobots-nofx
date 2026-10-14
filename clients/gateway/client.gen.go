// Code generated from contracts/gateway.openapi.yaml; DO NOT EDIT.
//
// Package gateway is the dependency-free Phase 1 client consumed by NoFX.
package gateway

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"
)

type Decimal string
type Mode string
type Side string
type OrderType string
type TimeInForce string
type OrderStatus string

const ModePaper Mode = "PAPER"

type Balance struct {
	Currency string  `json:"currency"`
	Total    Decimal `json:"total"`
	Free     Decimal `json:"free"`
	Locked   Decimal `json:"locked,omitempty"`
}

type NodeHealth struct {
	Node          string  `json:"node"`
	Account       string  `json:"account"`
	Reachable     bool    `json:"reachable"`
	LastHeartbeat *string `json:"last_heartbeat,omitempty"`
}

type ProjectionHealth struct {
	Reachable bool  `json:"reachable"`
	Head      int64 `json:"head"`
}

type Health struct {
	Status          string           `json:"status"`
	Version         string           `json:"version"`
	NautilusVersion string           `json:"nautilus_version"`
	Nodes           []NodeHealth     `json:"nodes"`
	Projection      ProjectionHealth `json:"projection"`
}

type Account struct {
	AccountID   string    `json:"account_id"`
	DisplayName string    `json:"display_name"`
	Mode        Mode      `json:"mode"`
	Venue       string    `json:"venue"`
	Node        string    `json:"node"`
	Balances    []Balance `json:"balances"`
}

type Position struct {
	AccountID     string   `json:"account_id"`
	Symbol        string   `json:"symbol"`
	Side          Side     `json:"side"`
	Qty           Decimal  `json:"qty"`
	AvgPx         Decimal  `json:"avg_px"`
	UnrealizedPnl *Decimal `json:"unrealized_pnl,omitempty"`
	RealizedPnl   *Decimal `json:"realized_pnl,omitempty"`
	OpenedAt      string   `json:"opened_at"`
}

type OrderRequest struct {
	AccountID   string       `json:"account_id"`
	Symbol      string       `json:"symbol"`
	Side        Side         `json:"side"`
	Qty         Decimal      `json:"qty"`
	OrderType   OrderType    `json:"order_type"`
	LimitPx     *Decimal     `json:"limit_px,omitempty"`
	TimeInForce *TimeInForce `json:"time_in_force,omitempty"`
	ReduceOnly  bool         `json:"reduce_only,omitempty"`
}

type Fill struct {
	TradeID            string   `json:"trade_id"`
	Qty                Decimal  `json:"qty"`
	Px                 Decimal  `json:"px"`
	Commission         *Decimal `json:"commission,omitempty"`
	CommissionCurrency *string  `json:"commission_currency,omitempty"`
	TsEvent            string   `json:"ts_event"`
}

type Order struct {
	ClientOrderID string       `json:"client_order_id"`
	VenueOrderID  *string      `json:"venue_order_id"`
	AccountID     string       `json:"account_id"`
	Symbol        string       `json:"symbol"`
	Side          Side         `json:"side"`
	Qty           Decimal      `json:"qty"`
	FilledQty     Decimal      `json:"filled_qty"`
	AvgPx         *Decimal     `json:"avg_px,omitempty"`
	OrderType     OrderType    `json:"order_type"`
	LimitPx       *Decimal     `json:"limit_px,omitempty"`
	TimeInForce   *TimeInForce `json:"time_in_force,omitempty"`
	Status        OrderStatus  `json:"status"`
	Mode          Mode         `json:"mode"`
	Reason        *string      `json:"reason"`
	Fills         []Fill       `json:"fills"`
	SubmittedAt   string       `json:"submitted_at"`
	UpdatedAt     string       `json:"updated_at"`
}

type Event struct {
	Seq       int64     `json:"seq"`
	Type      string    `json:"type"`
	AccountID string    `json:"account_id"`
	TsEvent   string    `json:"ts_event"`
	Order     *Order    `json:"order,omitempty"`
	Fill      *Fill     `json:"fill,omitempty"`
	Position  *Position `json:"position,omitempty"`
	Account   *Account  `json:"account,omitempty"`
}

type Error struct {
	Code    string         `json:"code"`
	Reason  string         `json:"reason"`
	Details map[string]any `json:"details,omitempty"`
}

type APIError struct {
	StatusCode int
	Body       Error
}

func (e *APIError) Error() string {
	return fmt.Sprintf("gateway %d %s: %s", e.StatusCode, e.Body.Code, e.Body.Reason)
}

type Client struct {
	BaseURL    string
	HTTPClient *http.Client
	Bearer     string
}

func NewClient(baseURL string, bearer string) *Client {
	return &Client{BaseURL: strings.TrimRight(baseURL, "/"), HTTPClient: http.DefaultClient, Bearer: bearer}
}

func (c *Client) do(ctx context.Context, method, path, idempotencyKey string, body any, out any) error {
	var payload *bytes.Reader
	if body == nil {
		payload = bytes.NewReader(nil)
	} else {
		encoded, err := json.Marshal(body)
		if err != nil {
			return err
		}
		payload = bytes.NewReader(encoded)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.BaseURL+path, payload)
	if err != nil {
		return err
	}
	if c.Bearer != "" {
		req.Header.Set("Authorization", "Bearer "+c.Bearer)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if idempotencyKey != "" {
		req.Header.Set("Idempotency-Key", idempotencyKey)
	}
	response, err := c.HTTPClient.Do(req)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode >= 400 {
		apiError := &APIError{StatusCode: response.StatusCode}
		if err := json.NewDecoder(response.Body).Decode(&apiError.Body); err != nil {
			return err
		}
		return apiError
	}
	return json.NewDecoder(response.Body).Decode(out)
}

func (c *Client) GetHealth(ctx context.Context) (Health, error) {
	var out Health
	err := c.do(ctx, http.MethodGet, "/v1/health", "", nil, &out)
	return out, err
}

func (c *Client) ListAccounts(ctx context.Context) ([]Account, error) {
	var out struct {
		Accounts []Account `json:"accounts"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/accounts", "", nil, &out)
	return out.Accounts, err
}

func (c *Client) GetAccount(ctx context.Context, accountID string) (Account, error) {
	var out Account
	err := c.do(ctx, http.MethodGet, "/v1/accounts/"+url.PathEscape(accountID), "", nil, &out)
	return out, err
}

func (c *Client) ListPositions(ctx context.Context, account string) ([]Position, string, error) {
	query := url.Values{}
	if account != "" {
		query.Set("account", account)
	}
	var out struct {
		Positions []Position `json:"positions"`
		AsOf      string     `json:"as_of"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/positions?"+query.Encode(), "", nil, &out)
	return out.Positions, out.AsOf, err
}

func (c *Client) ListOrders(ctx context.Context, account, status string, limit int) ([]Order, error) {
	query := url.Values{}
	if account != "" {
		query.Set("account", account)
	}
	if status != "" {
		query.Set("status", status)
	}
	if limit > 0 {
		query.Set("limit", strconv.Itoa(limit))
	}
	var out struct {
		Orders []Order `json:"orders"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/orders?"+query.Encode(), "", nil, &out)
	return out.Orders, err
}

func (c *Client) SubmitOrder(ctx context.Context, key string, input OrderRequest) (Order, error) {
	var out Order
	err := c.do(ctx, http.MethodPost, "/v1/orders", key, input, &out)
	return out, err
}

func (c *Client) GetOrder(ctx context.Context, clientOrderID string) (Order, error) {
	var out Order
	err := c.do(ctx, http.MethodGet, "/v1/orders/"+url.PathEscape(clientOrderID), "", nil, &out)
	return out, err
}

func (c *Client) CancelOrder(ctx context.Context, clientOrderID, key string) (Order, error) {
	var out Order
	err := c.do(ctx, http.MethodDelete, "/v1/orders/"+url.PathEscape(clientOrderID), key, nil, &out)
	return out, err
}

// EventsURL returns the resumable WebSocket endpoint. NoFX supplies its chosen
// WebSocket implementation and deduplicates frames by Event.Seq.
func (c *Client) EventsURL(account string, since *int64) string {
	query := url.Values{}
	if account != "" {
		query.Set("account", account)
	}
	if since != nil {
		query.Set("since", strconv.FormatInt(*since, 10))
	}
	base := strings.TrimPrefix(strings.TrimPrefix(c.BaseURL, "https://"), "http://")
	scheme := "ws://"
	if strings.HasPrefix(c.BaseURL, "https://") {
		scheme = "wss://"
	}
	return scheme + base + "/v1/events?" + query.Encode()
}
