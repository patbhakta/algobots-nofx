# Gateway Go client

`client.gen.go` is generated from `contracts/gateway.openapi.yaml` for the
NoFX integration. It intentionally uses only the Go standard library, so the
NoFX module can consume it without adding a runtime dependency.

The HTTP methods cover every OpenAPI operation. `EventsURL` exposes the
WebSocket URL while leaving the socket implementation to NoFX's existing
transport stack.
