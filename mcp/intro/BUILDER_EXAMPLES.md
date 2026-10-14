
4. [Function Calling](#function-calling)

---



```go
package main

import (
    "fmt"
    "nofx/mcp"
)

func main() {
    client := mcp.NewDeepSeekClientWithOptions(
        mcp.WithAPIKey("sk-xxx"),
    )

    request := mcp.NewRequestBuilder().
        WithSystemPrompt("You are a helpful assistant").
        WithUserPrompt("What is Go programming language?").
        Build()

    result, err := client.CallWithRequest(request)
    if err != nil {
        panic(err)
    }

    fmt.Println(result)
}
```


```go
result, err := client.CallWithMessages(
    "You are a helpful assistant",
    "What is Go?",
)

request := mcp.NewRequestBuilder().
    WithSystemPrompt("You are a helpful assistant").
    WithUserPrompt("What is Go?").
    Build()
result, err := client.CallWithRequest(request)
```

---



```go
request := mcp.NewRequestBuilder().
    AddSystemMessage("You are a trading advisor").
    AddUserMessage("Analyze BTC price").
    AddAssistantMessage("BTC is currently in an upward trend...").
    Build()

result, err := client.CallWithRequest(request)
```


```go
history := []mcp.Message{
    mcp.NewUserMessage("Hello"),
    mcp.NewAssistantMessage("Hi! How can I help?"),
    mcp.NewUserMessage("What's the weather?"),
    mcp.NewAssistantMessage("It's sunny today"),
}

request := mcp.NewRequestBuilder().
    AddSystemMessage("You are helpful").
    Build()

result, err := client.CallWithRequest(request)
```

---



```go
request := mcp.NewRequestBuilder().
    WithSystemPrompt("You are a Go expert").
    WithUserPrompt("Generate a HTTP server").
    WithMaxTokens(2000).
    Build()

code, err := client.CallWithRequest(request)
```


```go
request := mcp.NewRequestBuilder().
    WithSystemPrompt("You are a creative writer").
    WithUserPrompt("Write a sci-fi story about AI").
    WithMaxTokens(4000).
    Build()

story, err := client.CallWithRequest(request)
```


```go
request := mcp.NewRequestBuilder().
    WithSystemPrompt("You are a quantitative analyst").
    WithUserPrompt("Analyze BTC/USDT chart pattern").
    WithMaxTokens(1500).
    Build()

analysis, err := client.CallWithRequest(request)
```

---

## Function Calling


```go
weatherParams := map[string]any{
    "type": "object",
    "properties": map[string]any{
        "location": map[string]any{
            "type":        "string",
            "description": "City name, e.g., Beijing, Shanghai",
        },
        "unit": map[string]any{
            "type": "string",
            "enum": []string{"celsius", "fahrenheit"},
        },
    },
    "required": []string{"location"},
}

request := mcp.NewRequestBuilder().
    AddFunction(
    ).
    Build()

response, err := client.CallWithRequest(request)

```


```go
request := mcp.NewRequestBuilder().
    AddFunction("get_weather", "Get weather", weatherParams).
    AddFunction("calculate", "Calculate math", calcParams).
    AddFunction("search_web", "Search web", searchParams).
    WithToolChoice("auto").
    Build()

response, err := client.CallWithRequest(request)
```


```go
request := mcp.NewRequestBuilder().
    AddFunction("get_weather", "Get weather", weatherParams).
    WithToolChoice(`{"type": "function", "function": {"name": "get_weather"}}`).
    Build()

```

---



```go
request := mcp.ForChat().
    WithSystemPrompt("You are a friendly chatbot").
    WithUserPrompt("Hello!").
    Build()

request := mcp.NewRequestBuilder().
    WithSystemPrompt("You are a friendly chatbot").
    WithUserPrompt("Hello!").
    WithTemperature(0.7).
    WithMaxTokens(2000).
    Build()
```


```go
request := mcp.ForCodeGeneration().
    WithUserPrompt("Generate a REST API in Go").
    Build()

```


```go
// temperature=1.2, topP=0.95, maxTokens=4000
// presencePenalty=0.6, frequencyPenalty=0.5
request := mcp.ForCreativeWriting().
    WithSystemPrompt("You are a novelist").
    WithUserPrompt("Write a fantasy story").
    Build()

```

---



```go
package main

import (
    "fmt"
    "log"
    "nofx/mcp"
    "os"
)

func main() {
    client := mcp.NewDeepSeekClientWithOptions(
        mcp.WithAPIKey(os.Getenv("DEEPSEEK_API_KEY")),
        mcp.WithMaxRetries(5),
        mcp.WithTimeout(60 * time.Second),
    )

    analysisRequest := mcp.NewRequestBuilder().
        WithSystemPrompt("You are a professional quantitative trader").
        WithUserPrompt("Analyze BTC/USDT 1H chart, current price $45,000").
        WithMaxTokens(1500).
        Build()

    analysis, err := client.CallWithRequest(analysisRequest)
    if err != nil {
        log.Fatal(err)
    }
    fmt.Println("=== Market Analysis ===")
    fmt.Println(analysis)

    followUpRequest := mcp.NewRequestBuilder().
        AddSystemMessage("You are a professional quantitative trader").
        AddUserMessage("Analyze BTC/USDT 1H chart, current price $45,000").
        AddUserMessage("Based on your analysis, what's the best entry point?").
        WithTemperature(0.3).
        Build()

    entryPoint, err := client.CallWithRequest(followUpRequest)
    if err != nil {
        log.Fatal(err)
    }
    fmt.Println("\n=== Entry Point Suggestion ===")
    fmt.Println(entryPoint)
}
```


```go
func reviewCode(client mcp.AIClient, code string) (string, error) {
        WithSystemPrompt("You are a senior Go developer reviewing code").
        WithUserPrompt(fmt.Sprintf("Review this code:\n\n```go\n%s\n```", code)).
        WithMaxTokens(2000).
        AddStopSequence("---END---").
        Build()

    return client.CallWithRequest(request)
}

func main() {
    client := mcp.NewDeepSeekClientWithOptions(
        mcp.WithAPIKey(os.Getenv("DEEPSEEK_API_KEY")),
    )

    code := `
func Add(a, b int) int {
    return a + b
}
`

    review, err := reviewCode(client, code)
    if err != nil {
        log.Fatal(err)
    }
    fmt.Println(review)
}
```


```go
type ChatBot struct {
    client  mcp.AIClient
    history []mcp.Message
}

func NewChatBot(client mcp.AIClient, systemPrompt string) *ChatBot {
    return &ChatBot{
        client: client,
        history: []mcp.Message{
            mcp.NewSystemMessage(systemPrompt),
        },
    }
}

func (bot *ChatBot) Chat(userMessage string) (string, error) {
    bot.history = append(bot.history, mcp.NewUserMessage(userMessage))

    request := mcp.ForChat().
        AddMessages(bot.history...).
        Build()

    response, err := bot.client.CallWithRequest(request)
    if err != nil {
        return "", err
    }

    bot.history = append(bot.history, mcp.NewAssistantMessage(response))

    return response, nil
}

func main() {
    client := mcp.NewDeepSeekClientWithOptions(
        mcp.WithAPIKey(os.Getenv("DEEPSEEK_API_KEY")),
    )

    bot := NewChatBot(client, "You are a friendly and helpful assistant")

    resp1, _ := bot.Chat("What is Go?")
    fmt.Println("User: What is Go?")
    fmt.Println("Bot:", resp1)

    resp2, _ := bot.Chat("What are its main features?")
    fmt.Println("\nUser: What are its main features?")
    fmt.Println("Bot:", resp2)

    resp3, _ := bot.Chat("Show me an example")
    fmt.Println("\nUser: Show me an example")
    fmt.Println("Bot:", resp3)
}
```


```go
package main

import (
    "encoding/json"
    "fmt"
    "nofx/mcp"
    "os"
)

func getWeather(location string) string {
    return fmt.Sprintf("Weather in %s: Sunny, 25°C", location)
}

func main() {
    client := mcp.NewDeepSeekClientWithOptions(
        mcp.WithAPIKey(os.Getenv("DEEPSEEK_API_KEY")),
    )

    weatherParams := map[string]any{
        "type": "object",
        "properties": map[string]any{
            "location": map[string]any{
                "type":        "string",
                "description": "City name",
            },
        },
        "required": []string{"location"},
    }

    request := mcp.NewRequestBuilder().
        AddFunction("get_weather", "Get current weather", weatherParams).
        WithToolChoice("auto").
        Build()

    response, err := client.CallWithRequest(request)
    if err != nil {
        panic(err)
    }

    fmt.Println("AI Response:", response)

    // toolCall := parseToolCall(response)
    // weatherResult := getWeather(toolCall.Arguments.Location)

    // followUp := mcp.NewRequestBuilder().
    //     AddConversationHistory(previousMessages).
    //     AddToolResult(toolCall.ID, weatherResult).
    //     Build()
    //
    // finalResponse, _ := client.CallWithRequest(followUp)
}
```

---



```go
request, err := NewRequestBuilder().
    WithUserPrompt("Hello").
    Build()
if err != nil {
    log.Fatal(err)
}

request := NewRequestBuilder().
    WithSystemPrompt("You are helpful").
    WithUserPrompt("Hello").
```


```go
baseBuilder := mcp.NewRequestBuilder().
    WithSystemPrompt("You are a trading advisor").
    WithTemperature(0.3)

question1 := baseBuilder.
    AddUserMessage("Analyze BTC").
    Build()

question2 := baseBuilder.
    AddSystemMessage("You are a trading advisor").
    AddUserMessage("Analyze ETH").
    Build()
```


```go
ForCodeGeneration().WithUserPrompt("Generate code")

ForChat().WithUserPrompt("Hello")

ForCreativeWriting().WithUserPrompt("Write a story")

NewRequestBuilder().WithTemperature(0.6).WithUserPrompt("...")
```

---



```go
result, err := client.CallWithMessages("system", "user")

request := mcp.NewRequestBuilder().
    WithSystemPrompt("system").
    WithUserPrompt("user").
    Build()
result, err := client.CallWithRequest(request)

request := mcp.NewRequestBuilder().
    WithSystemPrompt("system").
    WithUserPrompt("user").
    Build()
result, err := client.CallWithRequest(request)
```

---

