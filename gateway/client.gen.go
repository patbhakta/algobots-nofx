// Code generated from contracts/gateway.openapi.yaml; DO NOT EDIT.
package gateway

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
)

type Decimal string
type Mode string

const ModePaper Mode = "PAPER"

type Balance struct {
	Currency string  `json:"currency"`
	Total    Decimal `json:"total"`
	Free     Decimal `json:"free"`
	Locked   Decimal `json:"locked,omitempty"`
}

type Account struct {
	AccountID   string    `json:"account_id"`
	DisplayName string    `json:"display_name"`
	Mode        Mode      `json:"mode"`
	Venue       string    `json:"venue"`
	Node        string    `json:"node"`
	Balances    []Balance `json:"balances"`
}

type Side string
type OrderType string

type OrderRequest struct {
	AccountID string    `json:"account_id"`
	Symbol    string    `json:"symbol"`
	Side      Side      `json:"side"`
	Qty       Decimal   `json:"qty"`
	OrderType OrderType `json:"order_type"`
	ReduceOnly bool     `json:"reduce_only,omitempty"`
}

type Order struct {
	ClientOrderID string  `json:"client_order_id"`
	VenueOrderID  *string `json:"venue_order_id"`
	Status        string  `json:"status"`
}

type Error struct {
	Code   string `json:"code"`
	Reason string `json:"reason"`
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

func NewClient(baseURL, bearer string) *Client {
	return &Client{BaseURL: strings.TrimRight(baseURL, "/"), HTTPClient: http.DefaultClient, Bearer: bearer}
}

func (c *Client) ListAccounts(ctx context.Context) ([]Account, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.BaseURL+"/v1/accounts", nil)
	if err != nil {
		return nil, err
	}
	if c.Bearer != "" {
		req.Header.Set("Authorization", "Bearer "+c.Bearer)
	}
	response, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode >= http.StatusBadRequest {
		apiErr := &APIError{StatusCode: response.StatusCode}
		if err := json.NewDecoder(response.Body).Decode(&apiErr.Body); err != nil {
			return nil, err
		}
		return nil, apiErr
	}
	var out struct {
		Accounts []Account `json:"accounts"`
	}
	if err := json.NewDecoder(response.Body).Decode(&out); err != nil {
		return nil, err
	}
	return out.Accounts, nil
}

func (c *Client) SubmitOrder(ctx context.Context, key string, input OrderRequest) (Order, error) {
	payload, err := json.Marshal(input)
	if err != nil {
		return Order{}, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.BaseURL+"/v1/orders", bytes.NewReader(payload))
	if err != nil {
		return Order{}, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Idempotency-Key", key)
	if c.Bearer != "" {
		req.Header.Set("Authorization", "Bearer "+c.Bearer)
	}
	response, err := c.HTTPClient.Do(req)
	if err != nil {
		return Order{}, err
	}
	defer response.Body.Close()
	if response.StatusCode >= http.StatusBadRequest {
		apiErr := &APIError{StatusCode: response.StatusCode}
		if err := json.NewDecoder(response.Body).Decode(&apiErr.Body); err != nil {
			return Order{}, err
		}
		return Order{}, apiErr
	}
	var out Order
	err = json.NewDecoder(response.Body).Decode(&out)
	return out, err
}
