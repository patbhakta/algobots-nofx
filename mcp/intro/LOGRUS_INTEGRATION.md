


```bash
go get github.com/sirupsen/logrus
```




```go
package main

import (
    "github.com/sirupsen/logrus"
    "nofx/mcp"
)

type LogrusLogger struct {
    logger *logrus.Logger
}

func NewLogrusLogger(logger *logrus.Logger) *LogrusLogger {
    return &LogrusLogger{logger: logger}
}

func (l *LogrusLogger) Debugf(format string, args ...any) {
    l.logger.Debugf(format, args...)
}

func (l *LogrusLogger) Infof(format string, args ...any) {
    l.logger.Infof(format, args...)
}

func (l *LogrusLogger) Warnf(format string, args ...any) {
    l.logger.Warnf(format, args...)
}

func (l *LogrusLogger) Errorf(format string, args ...any) {
    l.logger.Errorf(format, args...)
}
```


```go
package main

import (
    "github.com/sirupsen/logrus"
    "nofx/mcp"
)

func main() {
    logger := logrus.New()

    logger.SetLevel(logrus.DebugLevel)
    logger.SetFormatter(&logrus.JSONFormatter{})

    logrusAdapter := NewLogrusLogger(logger)

    client := mcp.NewClient(
        mcp.WithDeepSeekConfig("sk-xxx"),
    )

    result, err := client.CallWithMessages("system", "user")
    if err != nil {
        return
    }

}
```



```go
logger := logrus.New()
logger.SetFormatter(&logrus.JSONFormatter{
    TimestampFormat: "2006-01-02 15:04:05",
    PrettyPrint:     true,
})
```

```json
{
  "level": "info",
  "msg": "📡 [Provider: deepseek, Model: deepseek-chat] Request AI Server: BaseURL: https://api.deepseek.com/v1",
  "time": "2024-01-15 10:30:45"
}
```


```go
logger := logrus.New()
logger.WithFields(logrus.Fields{
    "service": "trading-bot",
    "version": "1.0.0",
})
```


```go
func createLogger(env string) *logrus.Logger {
    logger := logrus.New()

    switch env {
    case "production":
        logger.SetLevel(logrus.InfoLevel)
        logger.SetFormatter(&logrus.JSONFormatter{})

    case "development":
        logger.SetLevel(logrus.DebugLevel)
        logger.SetFormatter(&logrus.TextFormatter{
            FullTimestamp: true,
        })

    case "test":
        logger.SetLevel(logrus.FatalLevel)
    }

    return logger
}

logger := createLogger("production")
mcpClient := mcp.NewClient(
    mcp.WithLogger(NewLogrusLogger(logger)),
)
```


```go
package main

import (
    "os"

    "github.com/sirupsen/logrus"
    "nofx/mcp"
)

type LogrusLogger struct {
    logger *logrus.Logger
}

func NewLogrusLogger(logger *logrus.Logger) *LogrusLogger {
    return &LogrusLogger{logger: logger}
}

func (l *LogrusLogger) Debugf(format string, args ...any) {
    l.logger.Debugf(format, args...)
}

func (l *LogrusLogger) Infof(format string, args ...any) {
    l.logger.Infof(format, args...)
}

func (l *LogrusLogger) Warnf(format string, args ...any) {
    l.logger.Warnf(format, args...)
}

func (l *LogrusLogger) Errorf(format string, args ...any) {
    l.logger.Errorf(format, args...)
}

func main() {
    logger := logrus.New()
    logger.SetLevel(logrus.DebugLevel)
    logger.SetFormatter(&logrus.TextFormatter{
        FullTimestamp: true,
        ForceColors:   true,
    })
    logger.SetOutput(os.Stdout)

    client := mcp.NewDeepSeekClientWithOptions(
        mcp.WithAPIKey(os.Getenv("DEEPSEEK_API_KEY")),
        mcp.WithLogger(NewLogrusLogger(logger)),
        mcp.WithMaxRetries(5),
    )

    result, err := client.CallWithMessages(
    )

    if err != nil {
        return
    }

}
```



```
INFO[2024-01-15 10:30:45] 📡 [Provider: deepseek, Model: deepseek-chat] Request AI Server: BaseURL: https://api.deepseek.com/v1
DEBUG[2024-01-15 10:30:45] [Provider: deepseek, Model: deepseek-chat] UseFullURL: false
DEBUG[2024-01-15 10:30:45] [Provider: deepseek, Model: deepseek-chat]   API Key: sk-x...xxx
```


```json
{"level":"info","msg":"📡 [Provider: deepseek, Model: deepseek-chat] Request AI Server: BaseURL: https://api.deepseek.com/v1","time":"2024-01-15T10:30:45+08:00"}
```







- [MCP README](./README.md)
