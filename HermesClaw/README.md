# HermesClaw

HermesClaw is a graphical AI assistant application based on [OpenClaw](https://github.com/openclaw/openclaw).

## Structure

- **context/** - HermesClaw-specific context files (AGENTS.md, TOOLS.md)
- **electron/** - HermesClaw-specific Electron main process modules
- **extensions/** - HermesClaw extension configuration
- **runtime/** - HermesClaw runtime integration services

## Related Projects

- [OpenClaw](https://github.com/openclaw/openclaw) - Core AI assistant runtime
- [openclaw-instance/arsenal/sources/](../openclaw_instance/arsenal/sources/) - Source copies for reference

## Configuration

HermesClaw uses `~/.hermesclaw` for configuration and `~/.openclaw` for OpenClaw integration.