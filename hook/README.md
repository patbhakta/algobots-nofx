





```go
hook.RegisterHook(hook.GETIP, func(args ...any) any {
    userId := args[0].(string)
    return &hook.IpResult{IP: "192.168.1.1"}
})

result := hook.HookExec[hook.IpResult](hook.GETIP, "user123")
if result != nil && result.Error() == nil {
    ip := result.GetResult()
}
```


```go
func RegisterHook(key string, hook HookFunc)

func HookExec[T any](key string, args ...any) *T
```





```go
type IpResult struct {
    Err error
    IP  string
}
```


---




```go
type NewBinanceTraderResult struct {
    Err    error
}
```


---




```go
type NewAsterTraderResult struct {
    Err    error
}
```




```go
// proxy/init.go
package proxy

import "nofx/hook"

func InitHooks(enabled bool) {
    if !enabled {
    }

    hook.RegisterHook(hook.GETIP, func(args ...any) any {
        userId := args[0].(string)
        proxyIP, err := getProxyIP(userId)
        return &hook.IpResult{Err: err, IP: proxyIP}
    })

    hook.RegisterHook(hook.NEW_BINANCE_TRADER, func(args ...any) any {
        userId := args[0].(string)
        client := args[1].(*futures.Client)

        if client.HTTPClient != nil {
            client.HTTPClient.Transport = getProxyTransport()
        }

        return &hook.NewBinanceTraderResult{Client: client}
    })
}
```



```go
func InitHooks(enabled bool) {
    if !enabled {
    }
    hook.RegisterHook(KEY, hookFunc)
}

hook.RegisterHook(hook.GETIP, func(args ...any) any {
    ip, err := getIP()
    return &hook.IpResult{Err: err, IP: ip}  // ✅
})

userId, ok := args[0].(string)
if !ok {
}
```


```go
hook.RegisterHook(KEY, func(args ...any) any {
    if !enabled {
        return nil  // ❌
    }
    // ...
})

hook.RegisterHook(KEY, func(args ...any) any {
    if err != nil {
    }
})

```



```go
// hook/my_hook.go
package hook

type MyHookResult struct {
    Err    error
    Data   string
}

func (r *MyHookResult) Error() error {
    if r.Err != nil {
    }
    return r.Err
}

func (r *MyHookResult) GetResult() string {
    r.Error()
    return r.Data
}
```


```go
// hook/hooks.go
const (
    GETIP              = "GETIP"
    NEW_BINANCE_TRADER = "NEW_BINANCE_TRADER"
    NEW_ASTER_TRADER   = "NEW_ASTER_TRADER"
)
```


```go
result := hook.HookExec[hook.MyHookResult](hook.MY_HOOK, arg1, arg2)
if result != nil && result.Error() == nil {
    data := result.GetResult()
}
```


```go
hook.RegisterHook(hook.MY_HOOK, func(args ...any) any {
    return &hook.MyHookResult{Data: "result"}
})
```





```go
func TestHook(t *testing.T) {
    hook.Hooks = make(map[string]hook.HookFunc)

    hook.RegisterHook(hook.GETIP, func(args ...any) any {
        return &hook.IpResult{IP: "127.0.0.1"}
    })

    result := hook.HookExec[hook.IpResult](hook.GETIP, "test")
    assert.Equal(t, "127.0.0.1", result.IP)
}
```


