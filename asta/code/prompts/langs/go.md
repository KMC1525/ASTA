### Go
Use `go build/test/vet/fmt ./...`. Handle every error (`if err != nil`), wrap with `%w`, pass `context.Context` first, keep interfaces small and defined by the consumer, avoid goroutine leaks (always know how a goroutine ends), table-driven tests with `testing`. Keep `go.mod` tidy; add modules with `install_packages` (go) only when needed.
