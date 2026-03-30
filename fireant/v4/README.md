# FireAnt v4 — Signal-Based Agent Framework

A multi-agent system that builds software projects from high-level requirements. Agents coordinate through typed signals in Redis and write code into a layered dependency structure on disk.

## Overview

FireAnt v4 implements the architecture in `system_design.md`. Agents coordinate through four signal types in Redis (`task`, `task_done`, `fix_request`, `green`) instead of file-system artifacts. Code is organized into dependency layers (`layer_1/`, `layer_2/`, ...) enforcing an acyclic bottom-up build order.

- **Signal-based coordination** — Agents poll Redis for typed signals, no file-system stigmergy
- **Layered dependencies** — Code in `layer_n` may only depend on `layer_n-1` or lower
- **Decentralized execution** — Engineers and QA self-select work by claiming signals atomically
- **Executable feedback** — QA writes and runs tests; failures become `fix_request` signals
- **Incremental planning** — PM only plans based on verified (`green`) code

## Quick Start

### 1. Prerequisites

- Python 3.12+
- Redis server running locally

### 2. Install Dependencies

```bash
cd ConYard/fireant/v4
pip install -r requirements.txt
```

### 3. Configure API Key

```bash
cp secrets.yaml.example secrets.yaml
# Edit secrets.yaml and add your Gemini API key
```

Or set via environment variable:
```bash
export GEMINI_API_KEY="your-api-key-here"
```

### 4. Start Redis

```bash
redis-server
```

### 5. Run

```bash
python3 main.py --task "Build a snake game in JavaScript" --name "snake_game"
```

Results will be in `projects/snake_game_<timestamp>/`

Test the game:
```bash
cd projects/snake_game_<timestamp>
python3 -m http.server 8000
```

## Architecture

### Signal Model

```
PM  ──[task]──>  Engineer  ──[task_done]──>  QA Engineer
                     ^                            |
                     |                        pass? → [green] ──> PM
                     |                        fail? → [fix_request] ──> Engineer
```

| Signal | Producer | Consumer | Meaning |
|---|---|---|---|
| `task` | PM | Engineer | A granular coding task to implement |
| `task_done` | Engineer | QA | Code written, ready for testing |
| `fix_request` | QA | Engineer | Test failed, fix needed with failure details |
| `green` | QA | PM | File passed tests, code is verified |

### Agent Roles

| Agent | Trigger | Responsibility |
|---|---|---|
| **Manager** | User command | Creates PRD, answers questions, analyzes bugs |
| **PM** | Continuous loop | Gap analysis: PRD vs green code, pushes `task` signals |
| **Engineer** | `task` or `fix_request` signal | Claims signal, writes code, pushes `task_done` |
| **QA Engineer** | `task_done` signal | Writes + runs tests, pushes `green` or `fix_request` |

### Execution Flow

1. **Manager** creates the PRD from user task + template
2. **PM** reads PRD, identifies missing code, pushes `task` signals with layer assignments
3. **Engineers** (parallel) claim tasks, write code into `layer_n/`, push `task_done`
4. **QA** claims `task_done`, generates + executes tests
   - Pass → `green` signal (file verified)
   - Fail → `fix_request` signal back to Engineers
5. **PM** sees new `green` files, re-runs gap analysis, pushes next wave of tasks
6. **Convergence** — PM finds zero missing features, project is complete

### Layered Code Organization

```
project_root/
├── prd.md          # Requirements
├── index.html      # Entry point (Kaplay games)
├── package.json    # ES modules
├── layer_1/        # No dependencies (config, constants, pure logic)
├── layer_2/        # Depends only on layer_1/
├── layer_n/        # Depends on layer_(n-1) or lower
└── main.js         # Root entry point, wires everything (created last)
```

## Configuration

Edit `config.yaml`:

- **`agents`** — Per-agent LLM temperature and system prompts
- **`gemini`** — Model, token limits, concurrency
- **`redis`** — URL and key prefix
- **`workers`** — Number of parallel Engineers and QA workers
- **`escalation`** — Max retries before giving up
- **`logging`** — Level and output file

## Project Structure

```
v4/
├── main.py                 # CLI entry point, setup
├── config.yaml             # Configuration
├── secrets.yaml            # API key (not tracked)
├── system_design.md        # Full design doc
├── requirements.txt        # Python dependencies
├── templates/
│   └── kaplay_web_game.txt # Kaplay game template
├── agents/
│   ├── base.py             # BaseAgent (LLM client, file I/O)
│   ├── manager.py          # DO/ASK/DEBUG modes, README generation
│   ├── pm.py               # Gap analysis loop, task planning
│   ├── engineer.py         # Code writing from task/fix_request signals
│   └── qa_engineer.py      # Test generation + execution
├── orchestrator/
│   └── runner.py           # Thread spawning, PM loop, shutdown
└── utils/
    ├── config.py           # YAML config + secrets loader
    ├── signals.py          # Redis signal store (push/claim/peek)
    ├── gemini.py           # Gemini API wrapper with concurrency control
    └── operation_log.py    # JSONL operation logging
```

## Example Output

```
[signals] Connected to Redis at redis://localhost:6379
[manager] DO mode: Created PRD (template=kaplay_web_game.txt)
Started 3 engineer(s) and 1 QA worker(s)
[pm] ── Iteration 1/50 ──
[pm] Pushed task: config.js → layer_1
[pm] Pushed task: constants.js → layer_1
[engineer-0] Created config.js
[engineer-1] Created constants.js
[qa-0] PASSED: layer_1/config.js
[qa-0] PASSED: layer_1/constants.js
[pm] ── Iteration 2/50 ──
[pm] Pushed task: scenes.js → layer_2
...
[pm] Gap analysis returned 0 tasks — project complete!
[manager] Generated README.md
Project complete! Results in: projects/snake_game_20260330_093400/
```

## License

MIT

## References

- System design: `system_design.md`
- Mixture of Agents: https://arxiv.org/abs/2406.04692
