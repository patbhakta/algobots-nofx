




---



```go
mcpClient := mcp.New()
mcpClient.SetAPIKey(apiKey, url, model)

dsClient := mcp.NewDeepSeekClient()
qwenClient := mcp.NewQwenClient()
```


---



```go
client := mcp.NewClient(
    mcp.WithDeepSeekConfig("sk-xxx"),
    mcp.WithTimeout(60 * time.Second),
)
```


```go
type MyLogger struct {
    zapLogger *zap.Logger
}

func (l *MyLogger) Info(msg string, args ...any) {
    l.zapLogger.Sugar().Infof(msg, args...)
}

client := mcp.NewClient(
    mcp.WithLogger(&MyLogger{zapLogger}),
)
```


```go
customHTTP := &http.Client{
    Timeout: 30 * time.Second,
    Transport: &http.Transport{
        Proxy: http.ProxyFromEnvironment,
        TLSClientConfig: &tls.Config{/* ... */},
    },
}

client := mcp.NewClient(
    mcp.WithHTTPClient(customHTTP),
)
```


```go
func TestMyCode(t *testing.T) {
    mockHTTP := &MockHTTPClient{
    }

    client := mcp.NewClient(
        mcp.WithHTTPClient(mockHTTP),
        mcp.WithLogger(mcp.NewNoopLogger()),
    )

}
```


```go
client := mcp.NewDeepSeekClientWithOptions(
    mcp.WithAPIKey("sk-xxx"),
    mcp.WithLogger(customLogger),
    mcp.WithTimeout(60 * time.Second),
    mcp.WithMaxRetries(5),
    mcp.WithMaxTokens(4000),
)
```

---



|----------------|--------------|------|


|---------|------|---------|

---



```go
mcpClient := mcp.New()

if config.AIModel == "qwen" {
    mcpClient = mcp.NewQwenClient()
    mcpClient.SetAPIKey(config.QwenKey, config.CustomAPIURL, config.CustomModelName)
} else {
    mcpClient = mcp.NewDeepSeekClient()
    mcpClient.SetAPIKey(config.DeepSeekKey, config.CustomAPIURL, config.CustomModelName)
}

```


```go
var mcpClient mcp.AIClient

if config.AIModel == "qwen" {
    mcpClient = mcp.NewQwenClientWithOptions(
        mcp.WithAPIKey(config.QwenKey),
        mcp.WithBaseURL(config.CustomAPIURL),
        mcp.WithModel(config.CustomModelName),
    )
} else {
    mcpClient = mcp.NewDeepSeekClientWithOptions(
        mcp.WithAPIKey(config.DeepSeekKey),
        mcp.WithBaseURL(config.CustomAPIURL),
        mcp.WithModel(config.CustomModelName),
    )
}
```


```go
customLogger := &MyZapLogger{zap.NewProduction()}

mcpClient := mcp.NewDeepSeekClientWithOptions(
    mcp.WithAPIKey(config.DeepSeekKey),
)
```

---



```go
devClient := mcp.NewClient(
    mcp.WithDeepSeekConfig(apiKey),
)
```


```go
zapLogger, _ := zap.NewProduction()
prodClient := mcp.NewClient(
    mcp.WithDeepSeekConfig(apiKey),
    mcp.WithLogger(&ZapLogger{zapLogger}),
)
```


```go
mockHTTP := &MockHTTPClient{
    Response: `{"choices":[{"message":{"content":"test"}}]}`,
}

testClient := mcp.NewClient(
    mcp.WithHTTPClient(mockHTTP),
)
```


```go
proxyURL, _ := url.Parse("http://proxy.company.com:8080")
proxyClient := &http.Client{
    Transport: &http.Transport{
        Proxy: http.ProxyURL(proxyURL),
    },
}

client := mcp.NewClient(
    mcp.WithDeepSeekConfig(apiKey),
    mcp.WithHTTPClient(proxyClient),
)
```

---



### go.mod
```go
module github.com/yourorg/mcp

go 1.21

```

```go
import "github.com/yourorg/mcp"

client := mcp.NewClient(
    mcp.WithDeepSeekConfig("sk-xxx"),
)
```

---



```go
package mypackage_test

import (
    "testing"
    "github.com/stretchr/testify/assert"
    "nofx/mcp"
)

type MockHTTPClient struct {
    Response string
    Error    error
}

func (m *MockHTTPClient) Do(req *http.Request) (*http.Response, error) {
    if m.Error != nil {
        return nil, m.Error
    }

    return &http.Response{
        StatusCode: 200,
        Body:       io.NopCloser(strings.NewReader(m.Response)),
    }, nil
}

func TestAIIntegration(t *testing.T) {
    // Arrange
    mockHTTP := &MockHTTPClient{
        Response: `{"choices":[{"message":{"content":"success"}}]}`,
    }

    client := mcp.NewClient(
        mcp.WithHTTPClient(mockHTTP),
        mcp.WithLogger(mcp.NewNoopLogger()),
    )

    // Act
    result, err := client.CallWithMessages("system", "user")

    // Assert
    assert.NoError(t, err)
    assert.Equal(t, "success", result)
}
```

---






---



---



