# HermesClaw Project Brief

## Overview
HermesClaw is a "split-brain" synthesis architecture where:
- **OpenClaw** serves as the sensory-motor layer (messaging channels, canvas, websockets)
- **Hermes Agent** serves as the cognitive kernel (planning, memory, self-improvement loops)

## Core Objective
Build an autonomous AI agency platform (OROVA) that operates as a single-user tool, generating revenue by finding leads, sending outreach, booking meetings, and closing deals — all autonomously.

## Architecture
- **Gateway Port:** 18789 (OpenClaw gateway)
- **Dashboard Port:** 18790 (OROVA Mission Control)
- **Hermes Dashboard Port:** 9119 (Hermes standalone)
- **Dev Server Port:** 6969 (HermesClaw GUI dev)
- **Production GUI Port:** 3100 (HermesClaw GUI prod)

## Key Components
1. **Nova** — CEO Agent (cognitive kernel)
2. **9 Specialized Agents** — Atlas, Pixel, Quill, Hawk, Closer, Sentinel, Echo, Oracle, Viper
3. **9 Worker Lanes** — Fast Lane, Lead Hunt, Reply Monitor, Cold Escalation, Cloud Backup, CEO Brief, Health Monitor, Self-Improvement, Drip Sequence
4. **Semantic Firewall** — Tool call validation before execution
5. **Memory Bank** — Persistent context across sessions