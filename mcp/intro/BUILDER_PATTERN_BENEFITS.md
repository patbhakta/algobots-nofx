

---



```go
func (client *Client) buildMCPRequestBody(systemPrompt, userPrompt string) map[string]any {
    messages := []map[string]string{}

    if systemPrompt != "" {
        messages = append(messages, map[string]string{
            "role":    "system",
            "content": systemPrompt,
        })
    }
    messages = append(messages, map[string]string{
        "role":    "user",
        "content": userPrompt,
    })

    return map[string]interface{}{
        "model":       client.Model,
        "messages":    messages,
        "temperature": client.config.Temperature,
        "max_tokens":  client.MaxTokens,
    }
}
```





---



```go
client.CallWithCustomParams(
    "system prompt",
    "user prompt",
    0.5,              // frequency_penalty
    nil,              // stop sequences
    false,            // stream
)
```

```go
request := NewRequestBuilder().
    WithSystemPrompt("You are a helpful assistant").
    WithUserPrompt("Tell me about Go").
    WithTemperature(0.8).
    WithMaxTokens(2000).
    WithTopP(0.9).
    Build()

result, err := client.CallWithRequest(request)
```

---



```go
client.CallWithMessages("system", "user prompt")
```

```go
request := NewRequestBuilder().
    AddSystemMessage("You are a helpful assistant").
    AddUserMessage("What is the weather?").
    AddAssistantMessage("It's sunny today").
    WithTemperature(0.7).
    Build()
```


```go
```

```go
request := NewRequestBuilder().
    WithUserPrompt("What's the weather in Beijing?").
    AddTool(Tool{
        Type: "function",
        Function: FunctionDef{
            Name:        "get_weather",
            Description: "Get current weather",
            Parameters:  weatherParamsSchema,
        },
    }).
    WithToolChoice("auto").
    Build()
```


```go
```

```go
request := NewRequestBuilder().
    WithUserPrompt("Write a long story").
    WithStream(true).
    Build()

stream, err := client.CallStream(request)
for chunk := range stream {
    fmt.Print(chunk)
}
```

---



```go
func (client *Client) buildMCPRequestBody(
    systemPrompt, userPrompt string,
    topP float64,
    presencePenalty float64,
) map[string]any
```

```go
func (b *RequestBuilder) WithPresencePenalty(p float64) *RequestBuilder {
    b.presencePenalty = p
    return b
}

request := builder.WithUserPrompt("Hello").Build()

request := builder.
    WithUserPrompt("Hello").
    Build()
```

---


```go
client.CallWithParams(system, user, 0, 0, nil, nil)

client.CallWithParams(system, user, WithTopP(0.9), WithPenalty(0.5))

config := &RequestConfig{
    SystemPrompt: system,
    UserPrompt:   user,
    TopP:         0.9,
}
```

```go
request := NewRequestBuilder().
    WithUserPrompt("Hello").
    Build()

request := NewRequestBuilder().
    WithUserPrompt("Hello").
    WithTemperature(0.8).
    WithTopP(0.9).
    WithMaxTokens(2000).
    Build()
```

---


```go
```

```go
type RequestBuilder struct {
    messages    []Message
    temperature float64
    maxTokens   int
}

func (b *RequestBuilder) WithTemperature(t float64) *RequestBuilder {
    if t < 0 || t > 2 {
    }
    b.temperature = t
    return b
}

func (b *RequestBuilder) Build() (*Request, error) {
    if len(b.messages) == 0 {
        return nil, errors.New("at least one message is required")
    }
    if b.maxTokens <= 0 {
        return nil, errors.New("maxTokens must be positive")
    }
    return &Request{...}, nil
}
```

---



```go
request := NewRequestBuilder().
    AddSystemMessage("You are a quantitative trading advisor").
    AddUserMessage("Analyze BTC trend").
    AddAssistantMessage("BTC is in an upward trend based on...").
    WithMaxTokens(1000).
    Build()

analysis, err := client.CallWithRequest(request)
```


```go
request := NewRequestBuilder().
    WithSystemPrompt("You are a Go expert").
    WithUserPrompt("Generate a HTTP server").
    WithMaxTokens(2000).
    Build()
```


```go
request := NewRequestBuilder().
    WithSystemPrompt("You are a creative writer").
    WithUserPrompt("Write a sci-fi story").
    WithFrequencyPenalty(0.5).
    WithMaxTokens(4000).
    Build()
```


```go
weatherTool := Tool{
    Type: "function",
    Function: FunctionDef{
        Name:        "get_weather",
        Description: "Get current weather for a location",
        Parameters: map[string]any{
            "type": "object",
            "properties": map[string]any{
                "location": map[string]any{
                    "type":        "string",
                    "description": "City name",
                },
            },
            "required": []string{"location"},
        },
    },
}

request := NewRequestBuilder().
    WithUserPrompt("What's the weather in Beijing?").
    AddTool(weatherTool).
    WithToolChoice("auto").
    Build()

response, err := client.CallWithRequest(request)
```

---



```go
result, err := client.CallWithMessages(
    "You are a helpful assistant",
    "What is Go?",
)
```

```go
request := NewRequestBuilder().
    WithSystemPrompt("You are a helpful assistant").
    WithUserPrompt("What is Go?").
    Build()

result, err := client.CallWithRequest(request)
```


---


```go
result, err := client.CallWithMessagesAdvanced(
    "system prompt",
    "user prompt",
    nil,    // messages history?
    0.8,    // temperature
    2000,   // max_tokens
    0.9,    // top_p
    0.5,    // frequency_penalty
    0.6,    // presence_penalty
    nil,    // stop sequences
    false,  // stream
    nil,    // tools
    "",     // tool_choice
)
```

```go
request := NewRequestBuilder().
    WithSystemPrompt("system prompt").
    WithUserPrompt("user prompt").
    WithTemperature(0.8).
    WithMaxTokens(2000).
    WithTopP(0.9).
    WithFrequencyPenalty(0.5).
    WithPresencePenalty(0.6).
    Build()

result, err := client.CallWithRequest(request)
```


---





   - Function Calling / Tools






---



```go
result, err := client.CallWithMessages("system", "user")

request := NewRequestBuilder().
    WithUserPrompt("user").
    WithTemperature(0.8).
    Build()
result, err := client.CallWithRequest(request)
```

```go
```


```go
client.CallWithMessages("system", "user")

client.CallWithRequest(
    NewRequestBuilder().
        AddConversationHistory(history).
        AddUserMessage("new question").
        WithTools(tools).
        Build(),
)
```

---



```go
package mcp

type Message struct {
    Role    string `json:"role"`
    Content string `json:"content"`
}

type Tool struct {
    Type     string      `json:"type"`
    Function FunctionDef `json:"function"`
}

type Request struct {
    Model             string    `json:"model"`
    Messages          []Message `json:"messages"`
    Temperature       float64   `json:"temperature,omitempty"`
    MaxTokens         int       `json:"max_tokens,omitempty"`
    TopP              float64   `json:"top_p,omitempty"`
    FrequencyPenalty  float64   `json:"frequency_penalty,omitempty"`
    PresencePenalty   float64   `json:"presence_penalty,omitempty"`
    Stop              []string  `json:"stop,omitempty"`
    Tools             []Tool    `json:"tools,omitempty"`
    ToolChoice        string    `json:"tool_choice,omitempty"`
    Stream            bool      `json:"stream,omitempty"`
}

type RequestBuilder struct {
    model            string
    messages         []Message
    temperature      *float64
    maxTokens        *int
    topP             *float64
    frequencyPenalty *float64
    presencePenalty  *float64
    stop             []string
    tools            []Tool
    toolChoice       string
    stream           bool
}

func NewRequestBuilder() *RequestBuilder {
    return &RequestBuilder{
        messages: make([]Message, 0),
    }
}

func (b *RequestBuilder) WithModel(model string) *RequestBuilder {
    b.model = model
    return b
}

func (b *RequestBuilder) WithSystemPrompt(prompt string) *RequestBuilder {
    if prompt != "" {
        b.messages = append(b.messages, Message{
            Role:    "system",
            Content: prompt,
        })
    }
    return b
}

func (b *RequestBuilder) WithUserPrompt(prompt string) *RequestBuilder {
    b.messages = append(b.messages, Message{
        Role:    "user",
        Content: prompt,
    })
    return b
}

func (b *RequestBuilder) AddUserMessage(content string) *RequestBuilder {
    return b.WithUserPrompt(content)
}

func (b *RequestBuilder) AddSystemMessage(content string) *RequestBuilder {
    return b.WithSystemPrompt(content)
}

func (b *RequestBuilder) AddAssistantMessage(content string) *RequestBuilder {
    b.messages = append(b.messages, Message{
        Role:    "assistant",
        Content: content,
    })
    return b
}

func (b *RequestBuilder) AddMessage(role, content string) *RequestBuilder {
    b.messages = append(b.messages, Message{
        Role:    role,
        Content: content,
    })
    return b
}

func (b *RequestBuilder) AddConversationHistory(history []Message) *RequestBuilder {
    b.messages = append(b.messages, history...)
    return b
}

func (b *RequestBuilder) WithTemperature(t float64) *RequestBuilder {
    if t < 0 || t > 2 {
        panic("temperature must be between 0 and 2")
    }
    b.temperature = &t
    return b
}

func (b *RequestBuilder) WithMaxTokens(tokens int) *RequestBuilder {
    b.maxTokens = &tokens
    return b
}

func (b *RequestBuilder) WithTopP(p float64) *RequestBuilder {
    b.topP = &p
    return b
}

func (b *RequestBuilder) WithFrequencyPenalty(p float64) *RequestBuilder {
    b.frequencyPenalty = &p
    return b
}

func (b *RequestBuilder) WithPresencePenalty(p float64) *RequestBuilder {
    b.presencePenalty = &p
    return b
}

func (b *RequestBuilder) WithStopSequences(sequences []string) *RequestBuilder {
    b.stop = sequences
    return b
}

func (b *RequestBuilder) AddTool(tool Tool) *RequestBuilder {
    b.tools = append(b.tools, tool)
    return b
}

func (b *RequestBuilder) WithToolChoice(choice string) *RequestBuilder {
    b.toolChoice = choice
    return b
}

func (b *RequestBuilder) WithStream(stream bool) *RequestBuilder {
    b.stream = stream
    return b
}

func (b *RequestBuilder) Build() (*Request, error) {
    if len(b.messages) == 0 {
        return nil, errors.New("at least one message is required")
    }

    req := &Request{
        Model:      b.model,
        Messages:   b.messages,
        Stop:       b.stop,
        Tools:      b.tools,
        ToolChoice: b.toolChoice,
        Stream:     b.stream,
    }

    if b.temperature != nil {
        req.Temperature = *b.temperature
    }
    if b.maxTokens != nil {
        req.MaxTokens = *b.maxTokens
    }
    if b.topP != nil {
        req.TopP = *b.topP
    }
    if b.frequencyPenalty != nil {
        req.FrequencyPenalty = *b.frequencyPenalty
    }
    if b.presencePenalty != nil {
        req.PresencePenalty = *b.presencePenalty
    }

    return req, nil
}
```


```go
func (client *Client) CallWithRequest(req *Request) (string, error) {
    // ...
}
```

---



  - Function Calling


