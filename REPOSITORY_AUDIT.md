# Repository Audit

## Summary

- Repository: `SemosiKorea/market-chart`
- Local path: `/Users/kth/Desktop/market-signal`
- Branch: `market-signal-mvp-plan`
- Audited commit: `4895c4a`
- Current state: planning documents and captured chart images only; no application source code, test suite, runtime entrypoint, or deployment configuration existed before this first implementation pass.

## Existing Structure

- `AGENTS.md`: implementation guardrails for Codex work.
- `MARKET_SIGNAL_MVP_PLAN.md`: high-level MVP goal.
- `MVP_PRODUCT_SPEC.md`: product scope and validation questions.
- `MVP_ARCHITECTURE.md`: intended modules and domain model.
- `MVP_TASKS.md`: phased implementation checklist.
- `CODEX_FIRST_TASK.md`: first implementation instructions.
- `charts/`: historical chart image examples.

## Runtime And Dependencies

- Project Python is pinned with `uv` to Python `3.12.13`.
- Dependency management uses `pyproject.toml` and `uv.lock`.
- SQLite is available locally and is the intended first storage engine.
- No existing package layout, CLI, service entrypoint, Dockerfile, CI workflow, or deployment target was present.

## Credentials And Integrations

- No KIS or IBKR credentials are committed.
- No KIS or IBKR environment variables were present during the initial local check.
- TWS or IB Gateway was not found in `/Applications` during the initial local check.
- External provider integration tests must be skipped unless credentials and provider applications are configured.

## Implementation Adjustment

Because there was no existing application code to preserve, the first implementation uses a small `src/market_signal` Python package. The initial code is limited to provider-independent foundations: settings, domain models, time normalization, pricing quality calculations, and tests. Actual IBKR/KIS connections, SQLite persistence, comparison statistics, signal simulation, and reporting remain future phases.
