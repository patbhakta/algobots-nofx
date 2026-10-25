# Telegram Bot Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.




---











   - `api_key`
   - `secret_key`
   - `passphrase`




   - `config_strategy`
   - `config_exchange`
   - `config_model`
   - `config_trader`
   - `update_prompt`




---


```
telegram/
├── session/
├── intent/
├── service/
└── handler/

```

---


**Files:**
- Modify: `config/config.go`


```go
// Telegram Bot configuration
TelegramBotToken    string // TELEGRAM_BOT_TOKEN
TelegramAdminChatID int64  // TELEGRAM_ADMIN_CHAT_ID (only this user can operate)
```



```go
cfg.TelegramBotToken = os.Getenv("TELEGRAM_BOT_TOKEN")
if chatIDStr := os.Getenv("TELEGRAM_ADMIN_CHAT_ID"); chatIDStr != "" {
    if id, err := strconv.ParseInt(chatIDStr, 10, 64); err == nil {
        cfg.TelegramAdminChatID = id
    }
}
```



```bash
cd /Users/yida/gopro/open-nofx && go build ./...
```


**Step 4: Commit**

```bash
git add config/config.go
git commit -m "feat(telegram): add TelegramBotToken and TelegramAdminChatID to config"
```

---


**Files:**
- Create: `telegram/service/nofx.go`



```go
package service

import (
	"fmt"
	"nofx/manager"
	"nofx/store"
)

// NofxService is the single facade between Telegram bot and NOFX internals.
// All store/manager access MUST go through this layer.
type NofxService struct {
	store   *store.Store
	manager *manager.TraderManager
	userID  string // fixed user ID for single-user mode: "default"
}

func New(st *store.Store, tm *manager.TraderManager) *NofxService {
	return &NofxService{store: st, manager: tm, userID: "default"}
}

// --- Trader ---

func (s *NofxService) ListTraders() ([]store.Trader, error) {
	return s.store.Trader().List(s.userID)
}

func (s *NofxService) StartTrader(traderID string) error {
	t, err := s.store.Trader().Get(traderID)
	if err != nil {
		return fmt.Errorf("trader not found: %w", err)
	}
	return s.manager.StartTrader(t, s.store)
}

func (s *NofxService) StopTrader(traderID string) error {
	return s.manager.StopTrader(traderID)
}

// --- Strategy ---

func (s *NofxService) ListStrategies() ([]store.Strategy, error) {
	return s.store.Strategy().List(s.userID)
}

func (s *NofxService) CreateStrategy(name string, configJSON string) (*store.Strategy, error) {
	strategy := &store.Strategy{
		UserID: s.userID,
		Name:   name,
		Config: configJSON,
	}
	if err := s.store.Strategy().Create(strategy); err != nil {
		return nil, err
	}
	return strategy, nil
}

func (s *NofxService) UpdateStrategyPrompt(strategyID uint, prompt string) error {
	strategy, err := s.store.Strategy().Get(strategyID)
	if err != nil {
		return err
	}
	strategy.CustomPrompt = prompt
	return s.store.Strategy().Update(strategy)
}

// --- AI Model ---

func (s *NofxService) ListModels() ([]store.AIModel, error) {
	return s.store.AIModel().List(s.userID)
}

func (s *NofxService) CreateModel(provider, apiKey, model string) (*store.AIModel, error) {
	m := &store.AIModel{
		UserID:   s.userID,
		Provider: provider,
		APIKey:   apiKey,
		Model:    model,
	}
	if err := s.store.AIModel().Create(m); err != nil {
		return nil, err
	}
	return m, nil
}

// --- Exchange ---

func (s *NofxService) ListExchanges() ([]store.Exchange, error) {
	return s.store.Exchange().List(s.userID)
}

func (s *NofxService) CreateExchange(exchangeType, apiKey, secretKey string) (*store.Exchange, error) {
	ex := &store.Exchange{
		UserID:       s.userID,
		ExchangeType: exchangeType,
		APIKey:       apiKey,
		SecretKey:    secretKey,
	}
	if err := s.store.Exchange().Create(ex); err != nil {
		return nil, err
	}
	return ex, nil
}

// --- Positions / Query ---

func (s *NofxService) GetPositions(traderID string) ([]store.TraderPosition, error) {
	return s.store.Position().ListByTrader(traderID)
}

func (s *NofxService) GetEquitySummary(traderID string) (*store.EquitySnapshot, error) {
	return s.store.Equity().Latest(traderID)
}
```






```bash
cd /Users/yida/gopro/open-nofx && go build ./telegram/...
```


**Step 4: Commit**

```bash
git add telegram/service/nofx.go
git commit -m "feat(telegram): add NofxService facade layer"
```

---


**Files:**
- Create: `telegram/session/memory.go`



```go
package session

import (
	"fmt"
	"nofx/mcp"
	"strings"
)

const (
	// When short-term history exceeds this token estimate, trigger compaction
	compactionThresholdTokens = 3000
	// Rough estimate: 1 token ≈ 4 chars (Chinese ~2 chars/token)
	charsPerToken = 3
)

// Message represents a single conversation turn
type Message struct {
	Role    string // "user" or "assistant"
	Content string
}

// Memory manages conversation history with automatic compaction.
// Inspired by openclaw's compaction pattern.
type Memory struct {
	LongTerm  string    // Durable summary (survives compaction)
	ShortTerm []Message // Recent conversation (cleared on compaction)
	llm       mcp.AIClient
}

func NewMemory(llm mcp.AIClient) *Memory {
	return &Memory{llm: llm}
}

// Add appends a message and triggers compaction if needed
func (m *Memory) Add(role, content string) {
	m.ShortTerm = append(m.ShortTerm, Message{Role: role, Content: content})
	if m.estimateTokens() > compactionThresholdTokens {
		m.compact()
	}
}

// BuildContext returns context string for LLM intent parsing
func (m *Memory) BuildContext() string {
	var sb strings.Builder
	if m.LongTerm != "" {
		sb.WriteString(m.LongTerm)
		sb.WriteString("\n\n")
	}
	if len(m.ShortTerm) > 0 {
		for _, msg := range m.ShortTerm {
			sb.WriteString(fmt.Sprintf("%s: %s\n", msg.Role, msg.Content))
		}
	}
	return sb.String()
}

// Reset clears session (called on /start or new session)
func (m *Memory) Reset() {
	m.ShortTerm = []Message{}
	// LongTerm is preserved intentionally
}

func (m *Memory) estimateTokens() int {
	total := len(m.LongTerm)
	for _, msg := range m.ShortTerm {
		total += len(msg.Content)
	}
	return total / charsPerToken
}

// compact summarizes short-term history into long-term memory (silent, user doesn't see this)
func (m *Memory) compact() {
	if m.llm == nil || len(m.ShortTerm) == 0 {
		return
	}

	history := m.BuildContext()



	summary, err := m.llm.CallWithMessages(systemPrompt, history)
	if err != nil {
		// Compaction failed: keep short-term as-is, don't lose data
		return
	}

	// Write summary to long-term, clear short-term
	if m.LongTerm != "" {
		m.LongTerm = m.LongTerm + "\n" + summary
	} else {
		m.LongTerm = summary
	}
	m.ShortTerm = []Message{}
}
```


```bash
cd /Users/yida/gopro/open-nofx && go build ./telegram/...
```

**Step 3: Commit**

```bash
git add telegram/session/memory.go
git commit -m "feat(telegram): add conversation memory with openclaw-style compaction"
```

---


**Files:**
- Create: `telegram/session/session.go`


```go
package session

import (
	"nofx/mcp"
	"sync"
	"time"
)

// Intent represents what the user is currently trying to do
type Intent string

const (
	IntentNone            Intent = ""
	IntentConfigStrategy  Intent = "config_strategy"
	IntentConfigExchange  Intent = "config_exchange"
	IntentConfigModel     Intent = "config_model"
	IntentConfigTrader    Intent = "config_trader"
	IntentQueryPositions  Intent = "query_positions"
	IntentControlTrader   Intent = "control_trader"
	IntentUpdatePrompt    Intent = "update_prompt"
)

// Session holds state for a single Telegram conversation
type Session struct {
	ChatID    int64
	Intent    Intent
	Params    map[string]string // collected parameters so far
	Memory    *Memory
	UpdatedAt time.Time
}

// Manager manages all active sessions (one per chat ID)
type Manager struct {
	mu       sync.RWMutex
	sessions map[int64]*Session
	llm      mcp.AIClient
}

func NewManager(llm mcp.AIClient) *Manager {
	return &Manager{
		sessions: make(map[int64]*Session),
		llm:      llm,
	}
}

// Get returns or creates a session for the given chat ID
func (m *Manager) Get(chatID int64) *Session {
	m.mu.Lock()
	defer m.mu.Unlock()

	s, ok := m.sessions[chatID]
	if !ok {
		s = &Session{
			ChatID:    chatID,
			Intent:    IntentNone,
			Params:    make(map[string]string),
			Memory:    NewMemory(m.llm),
			UpdatedAt: time.Now(),
		}
		m.sessions[chatID] = s
	}
	s.UpdatedAt = time.Now()
	return s
}

// Reset clears session intent and params (keeps memory)
func (s *Session) Reset() {
	s.Intent = IntentNone
	s.Params = make(map[string]string)
}

// ResetFull clears everything including memory (on /start command)
func (s *Session) ResetFull() {
	s.Reset()
	s.Memory.Reset()
}
```




```bash
cd /Users/yida/gopro/open-nofx && go build ./telegram/...
```

**Step 3: Commit**

```bash
git add telegram/session/session.go
git commit -m "feat(telegram): add session state manager"
```

---


**Files:**
- Create: `telegram/intent/parser.go`



```go
package intent

import (
	"encoding/json"
	"nofx/mcp"
	"strings"
)

// ParsedIntent is the structured output from LLM intent parsing
type ParsedIntent struct {
	Action  string            `json:"action"`  // e.g. "config_strategy", "query_positions"
	Params  map[string]string `json:"params"`  // extracted parameters
	Missing []string          `json:"missing"` // params still needed
	Reply   string            `json:"reply"`   // what bot should say to user
}



{
  "action": "action_name",
  "params": {"key": "value"},
  "missing": ["param1", "param2"],
}


// Parser uses LLM to parse user message into structured intent
type Parser struct {
	llm mcp.AIClient
}

func NewParser(llm mcp.AIClient) *Parser {
	return &Parser{llm: llm}
}

// Parse sends user message + conversation context to LLM, returns structured intent
func (p *Parser) Parse(userMessage, conversationContext string) (*ParsedIntent, error) {
	userPrompt := userMessage
	if conversationContext != "" {
	}

	resp, err := p.llm.CallWithMessages(systemPrompt, userPrompt)
	if err != nil {
		return nil, err
	}

	// Extract JSON from response (LLM may wrap in markdown code block)
	jsonStr := extractJSON(resp)

	var result ParsedIntent
	if err := json.Unmarshal([]byte(jsonStr), &result); err != nil {
		// Fallback: return unknown intent with raw response as reply
		return &ParsedIntent{
			Action: "unknown",
		}, nil
	}
	return &result, nil
}

func extractJSON(s string) string {
	// Strip markdown code block if present
	s = strings.TrimSpace(s)
	if idx := strings.Index(s, "```json"); idx >= 0 {
		s = s[idx+7:]
	} else if idx := strings.Index(s, "```"); idx >= 0 {
		s = s[idx+3:]
	}
	if idx := strings.LastIndex(s, "```"); idx >= 0 {
		s = s[:idx]
	}
	// Find first { to last }
	start := strings.Index(s, "{")
	end := strings.LastIndex(s, "}")
	if start >= 0 && end > start {
		return s[start : end+1]
	}
	return s
}
```


```bash
cd /Users/yida/gopro/open-nofx && go build ./telegram/...
```

**Step 3: Commit**

```bash
git add telegram/intent/parser.go
git commit -m "feat(telegram): add LLM intent parser"
```

---


**Files:**
- Create: `telegram/handler/handler.go`



```go
package handler

import (
	"fmt"
	"nofx/telegram/intent"
	"nofx/telegram/service"
	"nofx/telegram/session"
	"strings"
)

// Handler dispatches parsed intents to the right operation
type Handler struct {
	svc     *service.NofxService
	parser  *intent.Parser
	sessions *session.Manager
}

func New(svc *service.NofxService, parser *intent.Parser, sessions *session.Manager) *Handler {
	return &Handler{svc: svc, parser: parser, sessions: sessions}
}

// Handle processes a user message and returns the bot reply
func (h *Handler) Handle(chatID int64, userMessage string) string {
	sess := h.sessions.Get(chatID)

	// Record user message in memory
	sess.Memory.Add("user", userMessage)

	// Build conversation context for LLM
	ctx := sess.Memory.BuildContext()

	// Parse intent via LLM
	parsed, err := h.parser.Parse(userMessage, ctx)
	if err != nil {
	}

	// Merge newly extracted params into session
	for k, v := range parsed.Params {
		sess.Params[k] = v
	}

	// If there are missing params, ask user
	if len(parsed.Missing) > 0 {
		sess.Intent = session.Intent(parsed.Action)
		reply := parsed.Reply
		sess.Memory.Add("assistant", reply)
		return reply
	}

	// Execute the action
	reply := h.execute(sess, parsed)
	sess.Memory.Add("assistant", reply)
	sess.Reset() // clear intent after successful execution
	return reply
}

func (h *Handler) execute(sess *session.Session, parsed *intent.ParsedIntent) string {
	params := sess.Params

	switch parsed.Action {
	case "config_strategy":
		return h.createStrategy(params)

	case "config_exchange":
		return h.createExchange(params)

	case "config_model":
		return h.createModel(params)

	case "query_positions":
		return h.queryPositions(params)

	case "query_equity":
		return h.queryEquity(params)

	case "control_start":
		return h.startTrader(params)

	case "control_stop":
		return h.stopTrader(params)

	case "update_prompt":
		return h.updatePrompt(params)

	default:
		return parsed.Reply
	}
}

func (h *Handler) createStrategy(params map[string]string) string {
	name := params["name"]
	if name == "" {
	}
	// Build a minimal strategy config JSON from params
	// Full StrategyConfig is complex; we start with essential fields
	configJSON := buildStrategyConfigJSON(params)
	strategy, err := h.svc.CreateStrategy(name, configJSON)
	if err != nil {
	}
}

func (h *Handler) createExchange(params map[string]string) string {
	exType := params["exchange_type"]
	apiKey := params["api_key"]
	secretKey := params["secret_key"]
	ex, err := h.svc.CreateExchange(exType, apiKey, secretKey)
	if err != nil {
	}
}

func (h *Handler) createModel(params map[string]string) string {
	provider := params["provider"]
	apiKey := params["api_key"]
	model := params["model"]
	m, err := h.svc.CreateModel(provider, apiKey, model)
	if err != nil {
	}
}

func (h *Handler) queryPositions(params map[string]string) string {
	traderID := params["trader_id"]
	if traderID == "" {
		traders, err := h.svc.ListTraders()
		if err != nil || len(traders) == 0 {
		}
		traderID = traders[0].ID
	}
	positions, err := h.svc.GetPositions(traderID)
	if err != nil {
	}
	if len(positions) == 0 {
	}
	var sb strings.Builder
	for _, p := range positions {
			p.Symbol, p.Side, p.EntryPrice, p.UnrealizedPnl))
	}
	return sb.String()
}

func (h *Handler) queryEquity(params map[string]string) string {
	traders, err := h.svc.ListTraders()
	if err != nil || len(traders) == 0 {
	}
	traderID := params["trader_id"]
	if traderID == "" {
		traderID = traders[0].ID
	}
	eq, err := h.svc.GetEquitySummary(traderID)
	if err != nil {
	}
}

func (h *Handler) startTrader(params map[string]string) string {
	traderID := params["trader_id"]
	if err := h.svc.StartTrader(traderID); err != nil {
	}
}

func (h *Handler) stopTrader(params map[string]string) string {
	traderID := params["trader_id"]
	if err := h.svc.StopTrader(traderID); err != nil {
	}
}

func (h *Handler) updatePrompt(params map[string]string) string {
	// strategy_id must be numeric; convert from params
	strategyIDStr := params["strategy_id"]
	var strategyID uint
	fmt.Sscanf(strategyIDStr, "%d", &strategyID)
	prompt := params["prompt"]
	if err := h.svc.UpdateStrategyPrompt(strategyID, prompt); err != nil {
	}
}

// buildStrategyConfigJSON builds a minimal valid StrategyConfig JSON from params
func buildStrategyConfigJSON(params map[string]string) string {
	coins := params["coins"]
	if coins == "" {
		coins = "BTC"
	}
	stopLoss := params["stop_loss_pct"]
	if stopLoss == "" {
		stopLoss = "5"
	}
	maxPos := params["max_position_pct"]
	if maxPos == "" {
		maxPos = "20"
	}
	indicators := params["indicators"]

	return fmt.Sprintf(`{
		"strategy_type": "ai_trading",
		"coin_source": {"source_type": "static", "static_coins": [%q]},
		"indicators": {"enable_rsi": %v, "enable_macd": %v},
		"risk_control": {"stop_loss_pct": %s, "max_position_pct": %s}
	}`,
		coins,
		strings.Contains(indicators, "RSI"),
		strings.Contains(indicators, "MACD"),
		stopLoss,
		maxPos,
	)
}

func formatParams(params map[string]string) string {
	var sb strings.Builder
	for k, v := range params {
		if k == "api_key" || k == "secret_key" {
			v = "***"
		}
		sb.WriteString(fmt.Sprintf("  %s: %s\n", k, v))
	}
	return sb.String()
}
```






   - `risk_control.stop_loss_pct`
   - `risk_control.max_position_pct`



```bash
cd /Users/yida/gopro/open-nofx && go build ./telegram/...
```

**Step 3: Commit**

```bash
git add telegram/handler/handler.go
git commit -m "feat(telegram): add intent handler with 6 feature areas"
```

---


**Files:**
- Create: `telegram/bot.go`


```go
package telegram

import (
	"nofx/config"
	"nofx/logger"
	"nofx/manager"
	"nofx/mcp"
	"nofx/store"
	"nofx/telegram/handler"
	"nofx/telegram/intent"
	"nofx/telegram/service"
	"nofx/telegram/session"

	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api/v5"
)

// Start initializes and runs the Telegram bot.
// Called from main.go as a goroutine.
func Start(cfg *config.Config, st *store.Store, tm *manager.TraderManager) {
	if cfg.TelegramBotToken == "" {
		logger.Info("📵 Telegram bot not configured (TELEGRAM_BOT_TOKEN not set), skipping")
		return
	}

	bot, err := tgbotapi.NewBotAPI(cfg.TelegramBotToken)
	if err != nil {
		logger.Errorf("❌ Failed to start Telegram bot: %v", err)
		return
	}

	logger.Infof("🤖 Telegram bot started: @%s", bot.Self.UserName)

	// Build the LLM client for intent parsing (use DeepSeek by default)
	llmClient := mcp.New()
	// Configure with whatever key is available in env (intent parsing is lightweight)
	// The service layer will use store to get user-configured models for actual trading

	svc := service.New(st, tm)
	parser := intent.NewParser(llmClient)
	sessions := session.NewManager(llmClient)
	h := handler.New(svc, parser, sessions)

	u := tgbotapi.NewUpdate(0)
	u.Timeout = 60
	updates := bot.GetUpdatesChan(u)

	for update := range updates {
		if update.Message == nil {
			continue
		}

		chatID := update.Message.Chat.ID

		// Access control: only allow configured admin chat ID
		if cfg.TelegramAdminChatID != 0 && chatID != cfg.TelegramAdminChatID {
			bot.Send(msg)
			continue
		}

		text := update.Message.Text
		if text == "" {
			continue
		}

		// Handle /start command
		if text == "/start" {
			sessions.Get(chatID).ResetFull()
			reply := tgbotapi.NewMessage(chatID, welcomeMessage())
			bot.Send(reply)
			continue
		}

		// Process message
		reply := h.Handle(chatID, text)
		msg := tgbotapi.NewMessage(chatID, reply)
		msg.ParseMode = "Markdown"
		bot.Send(msg)
	}
}

func welcomeMessage() string {





}
```




```bash
cd /Users/yida/gopro/open-nofx && go build ./telegram/...
```

**Step 3: Commit**

```bash
git add telegram/bot.go
git commit -m "feat(telegram): add Telegram bot entry point with access control"
```

---


**Files:**
- Modify: `main.go`



```go
"nofx/telegram"
```


```go
// Start API server
server := api.NewServer(...)
go func() { ... }()
```


```go
// Start Telegram bot (if configured)
go telegram.Start(cfg, st, traderManager)
logger.Info("🤖 Telegram bot goroutine started")
```


```bash
cd /Users/yida/gopro/open-nofx && go build -o nofx .
```


**Step 4: Commit**

```bash
git add main.go
git commit -m "feat(telegram): wire Telegram bot into main startup (3 lines)"
```

---


**Files:**


```env
# Telegram Bot Configuration
# Get token from @BotFather on Telegram
TELEGRAM_BOT_TOKEN=
# Get your chat ID from @userinfobot on Telegram
TELEGRAM_ADMIN_CHAT_ID=
```

**Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add Telegram bot configuration to .env.example"
```

---



```bash
```


```bash
cd /Users/yida/gopro/open-nofx && ./nofx
```

```
✅ Configuration loaded
🤖 Telegram bot started: @your_bot_name
✅ System started successfully
```





---






