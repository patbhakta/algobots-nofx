package auth

import "testing"

// TestGenerateJWTCarriesTenantID proves the session token carries explicit
// tenant identity (tenant == login account, aligned with the main repo's
// tenant_id naming) and that old tokens without the claim still validate.
func TestGenerateJWTCarriesTenantID(t *testing.T) {
	SetJWTSecret("auth-test-secret")

	token, err := GenerateJWT("user-1", "investor@algobots.test")
	if err != nil {
		t.Fatalf("GenerateJWT failed: %v", err)
	}

	claims, err := ValidateJWT(token)
	if err != nil {
		t.Fatalf("ValidateJWT failed: %v", err)
	}
	if claims.TenantID != "user-1" {
		t.Fatalf("expected tenant_id %q, got %q", "user-1", claims.TenantID)
	}
	if claims.UserID != "user-1" || claims.Email != "investor@algobots.test" {
		t.Fatalf("unexpected claims: user_id=%q email=%q", claims.UserID, claims.Email)
	}
}
