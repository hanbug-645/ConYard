# FireAnt — Hierarchical Stigmergic Agent Framework

A multi-agent system inspired by ant colony stigmergy, where LLM agents coordinate through a shared file system environment to build software projects from high-level requirements.

## Overview

FireAnt implements the system design described in `system_design.md`. Instead of agents communicating through messages, they coordinate by reading and writing artifacts (PRDs, manifests, code files, review feedback) in a hierarchical directory tree. This stigmergic approach enables:

- **Decentralized coordination** — No central controller; agents poll the file system and react to local state
- **Hierarchical decomposition** — Architect breaks down requirements into sub-components recursively
- **Upward escalation** — When implementation fails, feedback propagates up the tree for re-planning
- **Parallel redundancy** — High-risk components spawn competing approaches; a Voter selects the best
- **Executable feedback** — Tests run in each iteration; runtime errors guide bug fixes

## Quick Start

### 1. Install Dependencies

```bash
cd ConYard/fireant/v3
pip install -r requirements.txt
```

### 2. Configure API Key

```bash
cp config.yaml.example config.yaml
# Edit config.yaml and add your Gemini API key
```

Or set via environment variable:
```bash
export GEMINI_API_KEY="your-api-key-here"
```

### 3. Start Server Mode (Recommended)

```bash
python3 -m fireant.v3.main --server
```

Then use interactive commands:
```
fireant> DO build a snake game in js
fireant> STATUS
fireant> DEBUG 1227 the snake is not moving correctly
fireant> ASK how do I run this game?
```

### 4. Or Run One-Shot Mode

```bash
python3 -m fireant.v3.main \
  --task "Build a snake game in JavaScript" \
  --name "snake_game" \
  --max-iterations 50
```

Results will be in `projects/snake_game_<timestamp>/`

Run this to test the game:
```bash
python3 -m http.server 8000  
```

## Architecture

### Agent Roles

| Agent | Duty | Responsibility |
|---|---|---|
| **Manager** | Communication Layer | User interface, handles DO/ASK/DEBUG commands, creates initial PRD |
| **Architect** | Decomposition | Reads PRD, creates manifest with file/directory deliverables |
| **Engineer** | Implementation | Writes code for pending file deliverables |
| **Debugger** | Debug & Propagate | Fixes code on escalation, propagates issues up/down the tree |

### File System Artifacts

Every directory contains a standard file set:

- `prd.md` — Requirements for this scope
- `manifest.json` — Deliverables with status (`pending`, `in_progress`, `pass`, `fail`, `blocked`)
- `escalation.md` — Signals upward when local retries fail
- `vote_result.json` — Voter's scoring and selection rationale
- `status_pass.flag` — Created when all deliverables pass

### Execution Flow

**Server Mode (Interactive):**
1. User sends command (DO/ASK/DEBUG) → Manager
2. Manager delegates to technical agents
3. Pipeline runs in background
4. Manager displays results to user

**Pipeline (Automated):**
1. **Scan** — TreeScanner classifies each directory's state
2. **Roll-up** — Child statuses propagate to parent manifests (bottom-up)
3. **Dispatch** — Pipeline sends agents to directories in priority order:
   - Architect → Debugger → Engineer → QA
4. **Parallel** — Multiple agents can run on different directories simultaneously
5. **Repeat** — Loop until root is complete or max iterations reached

## Server Commands

When running in server mode, use these interactive commands:

| Command | Description | Example |
|---------|-------------|---------|
| `DO <task>` | Build a project from task description | `DO build a snake game in js` |
| `ASK <question>` | Ask about the current project | `ASK how do I run this game?` |
| `DEBUG <id> <instructions>` | Debug a project by identifier | `DEBUG 1227 snake not moving` |
| `STATUS` | Show current project status | `STATUS` |
| `STOP` | Stop running pipeline | `STOP` |
| `EXIT` | Shutdown server | `EXIT` |

**DEBUG Command Workflow:**
1. Manager finds project by identifier (e.g., "1227" from timestamp)
2. Debugger agent analyzes files and identifies issues
3. Debugger fixes problematic code
4. Manager displays results to user

## Configuration

Edit `config.yaml` to customize:

- **Per-agent temperatures** — Control LLM creativity per role
- **Orchestrator settings** — Max concurrent agents, iterations, poll interval
- **Escalation thresholds** — Max retries before escalating
- **Logging** — Level and output file

## Project Structure

```
v3/
├── main.py                 # Entry point
├── server.py               # Interactive server mode
├── config.yaml             # Configuration
├── secrets.yaml.example    # API key template
├── system_design.md        # Full design doc
├── agents/
│   ├── base.py             # BaseAgent with common utilities
│   ├── manager.py          # PRD creation, user commands
│   ├── architect.py        # Manifest creation, decomposition
│   ├── engineer.py         # Code implementation
│   └── debugger.py         # Escalation handling, code fixes
├── orchestrator/
│   ├── scanner.py          # TreeScanner (state classification)
│   └── pipeline.py         # Pipeline (dispatch loop)
└── utils/
    ├── config.py           # YAML + secrets loader, per-role config
    ├── gemini.py           # Gemini API wrapper with concurrency control
    ├── manifest.py         # Manifest CRUD, status roll-up
    └── operation_log.py    # JSONL operation logging
```

## Features

### ✅ Implemented

- Hierarchical decomposition (Architect)
- Code generation with contract awareness (Engineer)
- Escalation propagation with dead-loop prevention (Debugger)
- Interactive server mode (DO/ASK/DEBUG/STATUS commands)
- Manifest status roll-up (bottom-up)
- Parallel agent execution with concurrency control
- LLM call rate limiting via semaphore
- Operation logging (JSONL per project)
- Automatic README generation on project completion

### 🚧 Planned

- Risk assessment and parallel spawning (Strategist)
- Parallel candidate voting (Voter)
- Sandbox execution for tests (currently runs on host)
- File-level MoA (multiple `_candidate.js` files within a directory)
- Dynamic agent scaling based on workload density
- Agent-to-Agent (A2A) peer delegation

## Example Output

```
[pipeline] Starting on projects/snake_game_0321_1200 (max 50 iterations)
[architect] Planned projects/snake_game_0321_1200: 2 files + 3 subdirectories
[engineer] Created engine.js in projects/snake_game_0321_1200/game-logic
[pipeline] Project complete after 12 iterations
```

## License

MIT

## References

- System design: `system_design.md`
- Stigmergy: https://en.wikipedia.org/wiki/Stigmergy
- Mixture of Agents: https://arxiv.org/abs/2406.04692
- Tree of Thoughts: https://arxiv.org/abs/2305.10601
