package api

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"

	"nofx/auth"
	"nofx/manager"
	"nofx/store"

	"github.com/gin-gonic/gin"
)

// newTenantTestServer builds a Server backed by a fresh SQLite store with
// production route registration and a permissive auth throttle so tests are
// not rate-limited.
func newTenantTestServer(t *testing.T) (*Server, *store.Store) {
	t.Helper()
	gin.SetMode(gin.TestMode)
	auth.SetJWTSecret("tenant-test-secret")

	st, err := store.New(filepath.Join(t.TempDir(), "tenant-test.db"))
	if err != nil {
		t.Fatalf("failed to open test store: %v", err)
	}
	t.Cleanup(func() { _ = st.Close() })

	s := &Server{
		router:        gin.New(),
		traderManager: manager.NewTraderManager(),
		store:         st,
		authLimiter:   newIPRateLimiter(1000, 1000),
	}
	s.setupRoutes()
	return s, st
}

// doJSON performs an authenticated-or-anonymous JSON request against the
// test server and returns the recorder.
func doJSON(t *testing.T, s *Server, method, path, token string, body interface{}) *httptest.ResponseRecorder {
	t.Helper()
	var reader *bytes.Reader
	if body != nil {
		raw, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("failed to marshal request body: %v", err)
		}
		reader = bytes.NewReader(raw)
	} else {
		reader = bytes.NewReader(nil)
	}
	req := httptest.NewRequest(method, path, reader)
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	s.router.ServeHTTP(w, req)
	return w
}

type authResponse struct {
	Token    string `json:"token"`
	UserID   string `json:"user_id"`
	TenantID string `json:"tenant_id"`
	Email    string `json:"email"`
}

// registerTenant registers a tenant over HTTP and returns its session token.
func registerTenant(t *testing.T, s *Server, email string) authResponse {
	t.Helper()
	w := doJSON(t, s, http.MethodPost, "/api/register", "", map[string]string{
		"email":    email,
		"password": "TenantPass123!",
		"lang":     "en",
	})
	if w.Code != http.StatusOK {
		t.Fatalf("register %s: expected 200, got %d: %s", email, w.Code, w.Body.String())
	}
	var resp authResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("register %s: failed to parse response: %v", email, err)
	}
	return resp
}

type systemConfigResponse struct {
	Initialized         bool `json:"initialized"`
	RegistrationEnabled bool `json:"registration_enabled"`
}

func getSystemConfig(t *testing.T, s *Server) systemConfigResponse {
	t.Helper()
	w := doJSON(t, s, http.MethodGet, "/api/config", "", nil)
	if w.Code != http.StatusOK {
		t.Fatalf("GET /api/config: expected 200, got %d", w.Code)
	}
	var cfg systemConfigResponse
	if err := json.Unmarshal(w.Body.Bytes(), &cfg); err != nil {
		t.Fatalf("GET /api/config: failed to parse response: %v", err)
	}
	return cfg
}

// TestRegistrationToggleEndToEnd proves the backend-controlled registration
// gate: bootstrap registration allowed, closed once initialized, reopened by
// the operator setting, and duplicate emails rejected.
func TestRegistrationToggleEndToEnd(t *testing.T) {
	s, st := newTenantTestServer(t)

	// Fresh system: registration open for first-tenant bootstrap.
	if cfg := getSystemConfig(t, s); !cfg.RegistrationEnabled || cfg.Initialized {
		t.Fatalf("fresh system: expected registration_enabled=true initialized=false, got %+v", cfg)
	}

	tenantA := registerTenant(t, s, "tenant-a@algobots.test")

	// Token carries tenant identity; register response mirrors it.
	if tenantA.TenantID == "" || tenantA.TenantID != tenantA.UserID {
		t.Fatalf("register response: expected tenant_id == user_id, got user_id=%q tenant_id=%q", tenantA.UserID, tenantA.TenantID)
	}

	// Once initialized, registration defaults to closed (deployed behavior).
	if cfg := getSystemConfig(t, s); cfg.RegistrationEnabled || !cfg.Initialized {
		t.Fatalf("after first tenant: expected registration_enabled=false initialized=true, got %+v", cfg)
	}

	w := doJSON(t, s, http.MethodPost, "/api/register", "", map[string]string{
		"email": "tenant-b@algobots.test", "password": "TenantPass123!",
	})
	if w.Code != http.StatusForbidden {
		t.Fatalf("register while closed: expected 403, got %d: %s", w.Code, w.Body.String())
	}

	// Operator reopens registration via the persisted toggle.
	if err := st.SetSystemConfig("registration_enabled", "true"); err != nil {
		t.Fatalf("failed to enable registration: %v", err)
	}
	if cfg := getSystemConfig(t, s); !cfg.RegistrationEnabled {
		t.Fatalf("after enabling toggle: expected registration_enabled=true, got %+v", cfg)
	}

	tenantB := registerTenant(t, s, "tenant-b@algobots.test")
	if tenantB.UserID == "" || tenantB.UserID == tenantA.UserID {
		t.Fatalf("expected distinct tenant ids, got A=%q B=%q", tenantA.UserID, tenantB.UserID)
	}

	// Duplicate email is rejected regardless of the toggle.
	w = doJSON(t, s, http.MethodPost, "/api/register", "", map[string]string{
		"email": "tenant-b@algobots.test", "password": "TenantPass123!",
	})
	if w.Code != http.StatusConflict {
		t.Fatalf("duplicate email: expected 409, got %d", w.Code)
	}

	// Closing the toggle again shuts the door.
	if err := st.SetSystemConfig("registration_enabled", "false"); err != nil {
		t.Fatalf("failed to disable registration: %v", err)
	}
	w = doJSON(t, s, http.MethodPost, "/api/register", "", map[string]string{
		"email": "tenant-c@algobots.test", "password": "TenantPass123!",
	})
	if w.Code != http.StatusForbidden {
		t.Fatalf("register after closing toggle: expected 403, got %d", w.Code)
	}
}

// TestTenantSessionClaims proves the session token itself carries the tenant
// identity, and that login works for multiple tenants concurrently.
func TestTenantSessionClaims(t *testing.T) {
	s, st := newTenantTestServer(t)
	if err := st.SetSystemConfig("registration_enabled", "true"); err != nil {
		t.Fatalf("failed to enable registration: %v", err)
	}
	registerTenant(t, s, "a@algobots.test")
	tenantB := registerTenant(t, s, "b@algobots.test")

	w := doJSON(t, s, http.MethodPost, "/api/login", "", map[string]string{
		"email": "b@algobots.test", "password": "TenantPass123!",
	})
	if w.Code != http.StatusOK {
		t.Fatalf("login: expected 200, got %d: %s", w.Code, w.Body.String())
	}
	var login authResponse
	if err := json.Unmarshal(w.Body.Bytes(), &login); err != nil {
		t.Fatalf("login: failed to parse response: %v", err)
	}
	if login.TenantID != tenantB.TenantID {
		t.Fatalf("login tenant_id=%q, expected %q", login.TenantID, tenantB.TenantID)
	}

	claims, err := auth.ValidateJWT(login.Token)
	if err != nil {
		t.Fatalf("failed to validate login token: %v", err)
	}
	if claims.TenantID != tenantB.TenantID || claims.UserID != tenantB.TenantID {
		t.Fatalf("token claims: user_id=%q tenant_id=%q, expected %q", claims.UserID, claims.TenantID, tenantB.TenantID)
	}
}

type strategyListResponse struct {
	Strategies []struct {
		ID   string `json:"id"`
		Name string `json:"name"`
	} `json:"strategies"`
}

// TestCrossTenantIsolation is the security core of multi-tenant login:
// tenant B must never read tenant A's strategies, traders, trader config,
// exchanges or orders through the API, while tenant A still can.
func TestCrossTenantIsolation(t *testing.T) {
	s, st := newTenantTestServer(t)
	if err := st.SetSystemConfig("registration_enabled", "true"); err != nil {
		t.Fatalf("failed to enable registration: %v", err)
	}

	tenantA := registerTenant(t, s, "tenant-a@algobots.test")
	tenantB := registerTenant(t, s, "tenant-b@algobots.test")

	// Tenant A creates a private strategy.
	w := doJSON(t, s, http.MethodPost, "/api/strategies", tenantA.Token, map[string]interface{}{
		"name": "Tenant A private strategy",
		"lang": "en",
	})
	if w.Code != http.StatusOK {
		t.Fatalf("tenant A create strategy: expected 200, got %d: %s", w.Code, w.Body.String())
	}
	var created struct {
		ID string `json:"id"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &created); err != nil || created.ID == "" {
		t.Fatalf("tenant A create strategy: bad response %s (%v)", w.Body.String(), err)
	}
	strategyA := created.ID

	// Seed tenant A with a model, an exchange, and a trader (ownership is
	// what matters here, not trading viability).
	exchangeID, err := st.Exchange().Create(tenantA.UserID, "hyperliquid", "A main", true,
		"hl-test-key", "", "", false, "0x1111111111111111111111111111111111111111", true, false,
		"", "", "", "", "", "", 0)
	if err != nil {
		t.Fatalf("failed to seed exchange for tenant A: %v", err)
	}
	modelID := fmt.Sprintf("%s_deepseek", tenantA.UserID)
	if err := st.AIModel().Create(tenantA.UserID, modelID, "DeepSeek", "deepseek", true, "sk-test", ""); err != nil {
		t.Fatalf("failed to seed AI model for tenant A: %v", err)
	}
	traderID := "trader-tenant-a"
	if err := st.Trader().Create(&store.Trader{
		ID:             traderID,
		UserID:         tenantA.UserID,
		Name:           "A bot",
		AIModelID:      modelID,
		ExchangeID:     exchangeID,
		InitialBalance: 1000,
	}); err != nil {
		t.Fatalf("failed to seed trader for tenant A: %v", err)
	}

	// --- Strategy scoping ---
	w = doJSON(t, s, http.MethodGet, "/api/strategies", tenantB.Token, nil)
	if w.Code != http.StatusOK {
		t.Fatalf("tenant B list strategies: expected 200, got %d", w.Code)
	}
	var list strategyListResponse
	if err := json.Unmarshal(w.Body.Bytes(), &list); err != nil {
		t.Fatalf("tenant B list strategies: parse error %v", err)
	}
	for _, strat := range list.Strategies {
		if strat.ID == strategyA {
			t.Fatalf("SECURITY: tenant B sees tenant A strategy %q in list", strategyA)
		}
	}

	w = doJSON(t, s, http.MethodGet, "/api/strategies/"+strategyA, tenantB.Token, nil)
	if w.Code != http.StatusNotFound {
		t.Fatalf("tenant B fetch tenant A strategy: expected 404, got %d: %s", w.Code, w.Body.String())
	}
	// Control: tenant A can still fetch its own strategy.
	w = doJSON(t, s, http.MethodGet, "/api/strategies/"+strategyA, tenantA.Token, nil)
	if w.Code != http.StatusOK {
		t.Fatalf("tenant A fetch own strategy: expected 200, got %d", w.Code)
	}

	// --- Trader scoping ---
	w = doJSON(t, s, http.MethodGet, "/api/my-traders", tenantB.Token, nil)
	if w.Code != http.StatusOK {
		t.Fatalf("tenant B my-traders: expected 200, got %d", w.Code)
	}
	var traders []map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &traders); err != nil {
		t.Fatalf("tenant B my-traders: parse error %v", err)
	}
	if len(traders) != 0 {
		t.Fatalf("SECURITY: tenant B trader list not empty: %s", w.Body.String())
	}

	w = doJSON(t, s, http.MethodGet, "/api/traders/"+traderID+"/config", tenantB.Token, nil)
	if w.Code != http.StatusNotFound {
		t.Fatalf("tenant B fetch tenant A trader config: expected 404, got %d: %s", w.Code, w.Body.String())
	}
	// Control: tenant A can fetch its own trader config.
	w = doJSON(t, s, http.MethodGet, "/api/traders/"+traderID+"/config", tenantA.Token, nil)
	if w.Code != http.StatusOK {
		t.Fatalf("tenant A fetch own trader config: expected 200, got %d: %s", w.Code, w.Body.String())
	}

	// --- Exchange scoping ---
	w = doJSON(t, s, http.MethodGet, "/api/exchanges", tenantB.Token, nil)
	if w.Code != http.StatusOK {
		t.Fatalf("tenant B list exchanges: expected 200, got %d", w.Code)
	}
	if bytes.Contains(w.Body.Bytes(), []byte(exchangeID)) {
		t.Fatalf("SECURITY: tenant B sees tenant A exchange %q", exchangeID)
	}

	// --- Order scoping ---
	w = doJSON(t, s, http.MethodGet, "/api/orders?trader_id="+traderID, tenantB.Token, nil)
	if w.Code != http.StatusNotFound {
		t.Fatalf("tenant B fetch tenant A orders: expected 404, got %d: %s", w.Code, w.Body.String())
	}
	if bytes.Contains(w.Body.Bytes(), []byte("orders")) && !bytes.Contains(w.Body.Bytes(), []byte("not found")) {
		t.Fatalf("SECURITY: tenant B orders response leaked data: %s", w.Body.String())
	}
}
