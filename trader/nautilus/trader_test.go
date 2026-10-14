package nautilus

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGetBalancePreservesGatewayDecimals(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/accounts" {
			t.Fatalf("path = %q", r.URL.Path)
		}
		if got := r.Header.Get("Authorization"); got != "Bearer token" {
			t.Fatalf("authorization = %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"accounts":[{"account_id":"sandbox-1","display_name":"Sandbox","mode":"PAPER","venue":"SIM","node":"node-1","balances":[{"currency":"USDT","total":"1000.123456789012345678","free":"999.123456789012345678","locked":"1.000000000000000000"}]}]}`))
	}))
	defer server.Close()

	balance, err := NewTrader(server.URL, "token", "sandbox-1").GetBalance()
	if err != nil {
		t.Fatal(err)
	}
	if got := balance["total_equity"]; got != "1000.123456789012345678" {
		t.Fatalf("total_equity = %#v", got)
	}
	if got := balance["available_balance"]; got != "999.123456789012345678" {
		t.Fatalf("available_balance = %#v", got)
	}
}

func TestGetBalanceRejectsLiveAccount(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"accounts":[{"account_id":"live","mode":"LIVE","balances":[{"currency":"USD","total":"1","free":"1"}]}]}`))
	}))
	defer server.Close()
	if _, err := NewTrader(server.URL, "token", "live").GetBalance(); err == nil {
		t.Fatal("expected LIVE account rejection")
	}
}
