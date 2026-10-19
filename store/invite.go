package store

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

// TenantInvite ports A03's email-bound, hashed, expiring, single-use invite.
// Plaintext tokens are returned only at issuance and never persisted.
type TenantInvite struct {
	ID               string `gorm:"primaryKey"`
	Email            string `gorm:"not null"`
	TokenHash        string `gorm:"uniqueIndex;not null"`
	InvitedByUserID  string `gorm:"not null"`
	ExpiresAt        time.Time
	RedeemedAt       *time.Time
	RedeemedByUserID string
	CreatedAt        time.Time
}

type InviteAudit struct {
	ID          string `gorm:"primaryKey"`
	InviteID    string
	ActorUserID string
	Event       string
	CreatedAt   time.Time
}

func inviteHash(token string) string {
	sum := sha256.Sum256([]byte(token))
	return hex.EncodeToString(sum[:])
}

// IssueInvite restricts issuance to the existing owner, never an invitee.
func (s *UserStore) IssueInvite(actorID, email string) (string, error) {
	actor, err := s.GetByID(actorID)
	if err != nil || !strings.EqualFold(actor.Email, "pat@bhakta.us") {
		return "", errors.New("owner required")
	}
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		return "", err
	}
	token := hex.EncodeToString(raw)
	invite := TenantInvite{ID: uuid.NewString(), Email: strings.ToLower(strings.TrimSpace(email)), TokenHash: inviteHash(token), InvitedByUserID: actorID, ExpiresAt: time.Now().UTC().Add(7 * 24 * time.Hour)}
	err = s.db.Transaction(func(tx *gorm.DB) error {
		if err := tx.Create(&invite).Error; err != nil {
			return err
		}
		return tx.Create(&InviteAudit{ID: uuid.NewString(), InviteID: invite.ID, ActorUserID: actorID, Event: "invite.created"}).Error
	})
	if err != nil {
		return "", err
	}
	return token, nil
}

var ErrInvalidInvite = errors.New("valid unused invite required")

// RegisterInvited consumes the invite and creates the user in one transaction.
// The conditional update prevents concurrent redeemers from both succeeding.
func (s *UserStore) RegisterInvited(user *User, token string) error {
	if token == "" {
		return ErrInvalidInvite
	}
	user.Email = strings.ToLower(strings.TrimSpace(user.Email))
	return s.db.Transaction(func(tx *gorm.DB) error {
		now := time.Now().UTC()
		var invite TenantInvite
		if err := tx.Where("token_hash = ? AND email = ? AND redeemed_at IS NULL AND expires_at > ?", inviteHash(token), user.Email, now).First(&invite).Error; err != nil {
			return ErrInvalidInvite
		}
		result := tx.Model(&TenantInvite{}).Where("id = ? AND redeemed_at IS NULL AND expires_at > ?", invite.ID, now).Updates(map[string]interface{}{"redeemed_at": now, "redeemed_by_user_id": user.ID})
		if result.Error != nil {
			return result.Error
		}
		if result.RowsAffected != 1 {
			return ErrInvalidInvite
		}
		if err := tx.Create(user).Error; err != nil {
			return err
		}
		return tx.Create(&InviteAudit{ID: uuid.NewString(), InviteID: invite.ID, ActorUserID: user.ID, Event: "invite.redeemed"}).Error
	})
}
