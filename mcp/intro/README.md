# MCP - Model Context Protocol Client






```go
import "nofx/mcp"

client := mcp.NewClient(
    mcp.WithDeepSeekConfig("sk-xxx"),
)

result, err := client.CallWithMessages("system prompt", "user prompt")
if err != nil {
    log.Fatal(err)
}

fmt.Println(result)
```


```go
client := mcp.NewDeepSeekClientWithOptions(
    mcp.WithAPIKey("sk-xxx"),
    mcp.WithTimeout(60 * time.Second),
)
```


```go
client := mcp.NewQwenClientWithOptions(
    mcp.WithAPIKey("sk-xxx"),
    mcp.WithMaxTokens(4000),
)
```




```go
request := mcp.NewRequestBuilder().
    WithSystemPrompt("You are helpful").
    WithUserPrompt("What is Go?").
    WithTemperature(0.8).
    Build()

result, err := client.CallWithRequest(request)
```


```go
request := mcp.NewRequestBuilder().
    AddSystemMessage("You are a trading advisor").
    AddUserMessage("Analyze BTC").
    AddAssistantMessage("BTC is bullish...").
    WithTemperature(0.3).
    Build()

result, err := client.CallWithRequest(request)
```


```go
request := mcp.ForCodeGeneration().
    WithUserPrompt("Generate a HTTP server").
    Build()

request := mcp.ForCreativeWriting().
    WithUserPrompt("Write a story").
    Build()

request := mcp.ForChat().
    WithUserPrompt("Hello").
    Build()
```

#### Function Calling

```go
weatherParams := map[string]any{
    "type": "object",
    "properties": map[string]any{
        "location": map[string]any{"type": "string"},
    },
}

request := mcp.NewRequestBuilder().
    AddFunction("get_weather", "Get weather", weatherParams).
    WithToolChoice("auto").
    Build()

result, err := client.CallWithRequest(request)
```





```go
mcp.WithLogger(customLogger)

mcp.WithHTTPClient(customHTTP)
```


```go
mcp.WithTimeout(60 * time.Second)
mcp.WithMaxRetries(5)
mcp.WithRetryWaitBase(3 * time.Second)
```


```go
mcp.WithMaxTokens(4000)
mcp.WithTemperature(0.7)
```


```go
mcp.WithDeepSeekConfig("sk-xxx")

mcp.WithQwenConfig("sk-xxx")

mcp.WithAPIKey("sk-xxx")
mcp.WithBaseURL("https://api.custom.com")
mcp.WithModel("gpt-4")
```


```go
mockHTTP := &MockHTTPClient{
    Response: `{"choices":[{"message":{"content":"test"}}]}`,
}

client := mcp.NewClient(
    mcp.WithHTTPClient(mockHTTP),
)
```



```
    ↓
    ↓
    ├─ buildMCPRequestBody
    ├─ marshalRequestBody
    ├─ buildUrl
    ├─ setAuthHeader
    ├─ parseMCPResponse
    └─ isRetryableError
```


```go
type AIClient interface {
    SetAPIKey(...)
    SetTimeout(...)
    CallWithMessages(...) (string, error)
}

type clientHooks interface {
    buildMCPRequestBody(...) map[string]any
    buildUrl() string
    setAuthHeader(...)
    marshalRequestBody(...) ([]byte, error)
    parseMCPResponse(...) (string, error)
    isRetryableError(...) bool
}
```



```go
client := mcp.New()
client.SetAPIKey("sk-xxx", "https://api.custom.com", "gpt-4")

dsClient := mcp.NewDeepSeekClient()
dsClient.SetAPIKey("sk-xxx", "", "")
```


```go
// go.mod
module github.com/yourorg/yourproject

require github.com/yourorg/mcp v1.0.0
```

```go
// main.go
import "github.com/yourorg/mcp"

client := mcp.NewClient(
    mcp.WithDeepSeekConfig("sk-xxx"),
)
```


```go
type CustomProvider struct {
    *mcp.Client
}

func (c *CustomProvider) buildUrl() string {
    return c.BaseURL + "/custom/endpoint"
}

func (c *CustomProvider) setAuthHeader(headers http.Header) {
    headers.Set("X-Custom-Auth", c.APIKey)
}
```



```go
type ZapLogger struct {
    logger *zap.Logger
}

func (l *ZapLogger) Infof(format string, args ...any) {
    l.logger.Sugar().Infof(format, args...)
}

func (l *ZapLogger) Debugf(format string, args ...any) {
    l.logger.Sugar().Debugf(format, args...)
}

client := mcp.NewClient(
    mcp.WithLogger(&ZapLogger{zapLogger}),
)
```


```go
type LogrusLogger struct {
    logger *logrus.Logger
}

func (l *LogrusLogger) Infof(format string, args ...any) {
    l.logger.Infof(format, args...)
}

func (l *LogrusLogger) Debugf(format string, args ...any) {
    l.logger.Debugf(format, args...)
}
```



```go
devClient := mcp.NewClient(
    mcp.WithDeepSeekConfig("sk-xxx"),
)
```


```go
prodClient := mcp.NewClient(
    mcp.WithDeepSeekConfig("sk-xxx"),
)
```


```go
testClient := mcp.NewClient(
    mcp.WithHTTPClient(mockHTTP),
    mcp.WithLogger(mcp.NewNoopLogger()),
)
```






- Go 1.18+




MIT License


