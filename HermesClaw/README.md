# HermesClaw

HermesClaw is a graphical AI assistant application based on [OpenClaw](https://github.com/openclaw/openclaw).

## Structure

- **context/** - HermesClaw-specific context files (AGENTS.md, TOOLS.md)
- **electron/** - HermesClaw-specific Electron main process modules
- **extensions/** - HermesClaw extension configuration
- **runtime/** - HermesClaw runtime integration services

> **Note:** the files in this folder are reference mirrors. The canonical,
> compiled sources live in the repository root: runtime services under
> `../electron/runtime/services/`, the semantic firewall under
> `../electron/runtime/security/`, and its unit tests under
> `../tests/unit/`. Edit the canonical files and copy them here to keep the
> mirrors in sync.

## Related Projects

- [OpenClaw](https://github.com/openclaw/openclaw) - Core AI assistant runtime
- [openclaw-instance/arsenal/sources/](../openclaw_instance/arsenal/sources/) - Source copies for reference

## Configuration

HermesClaw uses `~/.hermesclaw` for configuration and `~/.openclaw` for OpenClaw integration.