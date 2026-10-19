package store

import (
	"github.com/google/uuid"
	"path/filepath"
	"testing"
	"time"
)

func TestInviteLifecycle(t *testing.T) {
	st, err := New(filepath.Join(t.TempDir(), "invite.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	owner := &User{ID: uuid.NewString(), Email: "pat@bhakta.us", PasswordHash: "existing-owner-hash"}
	if err := st.User().Create(owner); err != nil {
		t.Fatal(err)
	}
	for _, kind := range []string{"missing", "bad", "expired", "wrong-email", "valid"} {
		t.Run(kind, func(t *testing.T) {
			email := kind + "@example.com"
			token, err := st.User().IssueInvite(owner.ID, email)
			if err != nil {
				t.Fatal(err)
			}
			var row TenantInvite
			if err := st.GormDB().Where("token_hash = ?", inviteHash(token)).First(&row).Error; err != nil {
				t.Fatal(err)
			}
			if row.TokenHash == token {
				t.Fatal("plaintext persisted")
			}
			switch kind {
			case "missing":
				token = ""
			case "bad":
				token = "invalid"
			case "expired":
				st.GormDB().Model(&row).Update("expires_at", time.Now().Add(-time.Hour))
			case "wrong-email":
				email = "other@example.com"
			}
			user := &User{ID: uuid.NewString(), Email: email, PasswordHash: "hash"}
			err = st.User().RegisterInvited(user, token)
			if kind != "valid" {
				if err == nil {
					t.Fatal("accepted invalid invite")
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			if err := st.User().RegisterInvited(&User{ID: uuid.NewString(), Email: email, PasswordHash: "hash"}, token); err == nil {
				t.Fatal("accepted used invite")
			}
			if _, err := st.User().IssueInvite(user.ID, "next@example.com"); err == nil {
				t.Fatal("non-owner issued invite")
			}
		})
	}
	got, err := st.User().GetByID(owner.ID)
	if err != nil || got.PasswordHash != owner.PasswordHash {
		t.Fatal("owner changed")
	}
	var count int64
	st.GormDB().Model(&InviteAudit{}).Where("event = ?", "invite.redeemed").Count(&count)
	if count != 1 {
		t.Fatalf("redemption audits: %d", count)
	}
}
