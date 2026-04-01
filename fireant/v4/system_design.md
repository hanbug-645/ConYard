# System Design: Signal-Based Coordination

## 1. The Environment

Instead of a single message pool or file-system stigmergy, the environment uses a **Redis in-memory store** to track coordination and a **file system** to track artifacts (code and PRDs).

- **The Signal Table:** Agents coordinate purely through typed signals stored in Redis.
- **Layered Code Organization:** Source code is organized strictly by dependency layers on the physical file system:
  - **Root:** The Manager creates initial entry point files and the `prd.md` here.
  - **`layer_1/`:** The first wave of code written by Engineers. This code has **no dependencies** other than basic standard libraries.
  - **`layer_n/`:** Subsequent code is placed in layers based on its dependencies. If a new file depends on code in `layer_n`, it must be placed in `layer_n+1`. This enforces a strict, acyclic, bottom-up dependency graph.
- **Decentralized Coordination:** Agents continuously poll Redis for signals they care about. There is no central orchestrator assigning work; agents self-select tasks based on their roles.

---

## 2. The Signal Model

The full lifecycle of a task flows through Redis signals:

```text
PM  ──[task]──►  Engineer  ──[task_done]──►  QA Engineer
                     ▲                            │
                     │                        pass? → [green]
                     │                        fail? → [fix_request] ──►  Engineer
                     │
PM  ◄── (reads green files + existing code to decide next step)
```

### Signal Types

| Signal | Producer | Consumer | Meaning |
|---|---|---|---|
| `task` | PM | Engineer | A granular coding task to implement |
| `task_done` | Engineer | QA Engineer | Code written, ready for testing |
| `fix_request` | QA Engineer | Engineer | Test failed — fix needed, includes failure details |
| `green` | QA Engineer | PM | File passed tests, code is verified |

---

## 3. Agent Roles and Triggers

LLM agents observe the Redis signal table and execute specific tasks based on their assigned roles.

### A. Manager (Communication Layer)

- **Goal:** Interface between user and technical agents. Handle user communication and coordinate agent activities.
- **Trigger:** Called directly by server for user commands (DO, ASK, DEBUG).
- **Actions:**
  - **DO mode:** Creates initial PRD from user task on disk. Kicks off the system.
  - **ASK mode:** Answers user questions using LLM with project context.
  - **DEBUG mode:** Analyzes user-reported issues.
  - **README generation:** After the task is completed, generates comprehensive README.
- **Scope:** Communication only. Does **not** write code or tests.

### B. Product Manager (PM) (Requirements & Planning)

- **Goal:** Drive the project forward by finding the gap between the target and current state.
- **Trigger:** Continuous loop, pausing to wait for `green` signals.
- **Action:** Reads the PRD (target state) and reads the current verified code on disk (indicated by `green` signals). Identifies what is missing. Determines the appropriate layer for the next piece of code based on dependencies, and creates granular `task` signals in Redis for Engineers.
- **Scope:** Planning and dependency tracking only. Does **not** write code. Does not assign tasks to specific Engineers.

### C. Engineer (Implementation)

- **Goal:** Execute granular coding tasks as individual contractors.
- **Trigger:** Presence of an unclaimed `task` or `fix_request` signal in Redis.
- **Action (Evaluate-then-Act):**
  1. Atomically claims a task from Redis.
  2. **Evaluates feasibility** — asks the LLM: "Can I complete this file with the current green code?"
     - **Path A (completable):** Determines which green files are dependencies, resolves the correct layer, and writes the code.
     - **Path B (not completable):** Identifies a missing helper, writes that smaller sub-task first, then re-queues the original task for a future iteration.
  3. Writes the code to disk and deposits a `task_done` signal in Redis.
  4. For `fix_request` signals, skips evaluation and goes straight to fixing.
- **Scope:** Code implementation only. Does **not** plan at the project level or write tests. Embarrassingly parallel (multiple Engineers run concurrently).

### D. QA Engineer (Quality Assurance)

- **Goal:** Write and execute unit tests for code, providing executable feedback.
- **Trigger:** A `task_done` signal in Redis.
- **Action:**
  1. Reads the newly written code.
  2. Writes corresponding unit test cases.
  3. Physically executes the tests in a secure sandbox.
  4. **On pass:** Leaves a `green` signal in Redis, verifying the code for the PM.
  5. **On fail:** Leaves a `fix_request` signal in Redis containing the failure details for an Engineer to pick up.
- **Scope:** Test writing and execution only. Does **not** write application code or create PM-level tasks.

---

## 4. Execution Flow (Emergent Behavior)

Control propagates through the signal loop, allowing the system to self-organize and adapt.

### 4.1 The Core Loop

1. **Startup:** Manager creates the PRD and initial root entry points on disk, then starts the PM.
2. **PM gap analysis:** PM reads the PRD and the current code, identifies the immediate next steps, determines their dependency layer (e.g., `layer_1` for initial tasks), and pushes `task` signals to Redis.
3. **Engineers build:** Engineers claim `task` signals, write code into the appropriate `layer_n` directory, and push `task_done` signals.
4. **QA verifies:** QA Engineer consumes `task_done` signals, writes/runs tests against the new layer code.
   - If tests pass, pushes a `green` signal.
   - If tests fail, pushes a `fix_request` signal back to the Engineers.
5. **PM iterates:** Once files turn `green`, the PM wakes up, re-reads the existing verified code across all layers, and decides the next step (which will likely depend on `layer_n` and thus be placed in `layer_n+1`), pushing new `task` signals.
6. **Convergence:** The project is complete when the PM runs a gap analysis and finds no difference between the PRD requirements and the verified `green` code.

### 4.2 The Debug Flow (Executable Feedback Loop)

When a bug is introduced, the system relies on an **Executable Feedback Loop**:

1. **Code Deposition:** The Engineer agent writes code and leaves a `task_done` signal.
2. **Test Generation & Execution:** The QA Engineer writes and runs tests.
3. **The Error Signal:** If the code fails, QA leaves a `fix_request` signal with the test failure output.
4. **Self-Correction (Debugging):** An Engineer picks up the `fix_request`, reads the failing code and the test output, and overwrites the code file with a fix, leaving a new `task_done` signal.

### 4.3 Feature Requests

1. **The Top-Level Stimulus:** The user provides a new requirement.
2. **Manager Update:** The Manager updates the root PRD on disk.
3. **PM Gap Analysis:** The PM runs its loop, sees the new PRD requirements, notices they aren't implemented in the existing verified code, and pushes new `task` signals to Redis to build the feature.

---

## 5. Agent Context Building

Agents receive **function/type signatures with descriptions** instead of raw code excerpts. This is more token-efficient and semantically richer than truncated file contents.

### 5.1 Code Summarization (`utils/code_summary.py`)

For each green file, the system extracts:
- **JS/TS:** exported constants, function signatures (name + params), class declarations, JSDoc/comments as descriptions.
- **Python:** `def`/`async def` signatures with type annotations, `class` declarations, docstrings as descriptions.

Example output instead of 60 lines of raw code:
```
--- layer_1/constants.js ---
export const TILE_SIZE = 32
export const GRAVITY = 800
createConfig(difficulty) — Build game config for the given difficulty level.
```

### 5.2 Layer-Aware Context Filtering

When building context for code generation, the Engineer only sees files from **lower layers**:

| Target layer | Context includes |
|---|---|
| `layer_1` | Nothing (no lower layers exist) |
| `layer_2` | `layer_1/` files only |
| `layer_N` | `layer_1/` through `layer_(N-1)/` |
| Root (`""`) | **ALL** layers (root wires everything) |

Files within the same layer are treated as siblings, not dependencies, and are excluded.

### 5.3 Context Ordering

Within the included layers, files are sorted by **layer depth descending** — highest (closest dependency) first. This puts the most relevant context at the top of the LLM prompt.

### 5.4 Evaluation Context

The Engineer's task evaluation step (`_evaluate_task`) uses **all** green files (unfiltered) to assess feasibility. Layer filtering is only applied during code generation.

---

## 6. Fault Tolerance

The system is designed to recover from failures at every level without human intervention.

### 6.1 File Deletion on Retry Exhaustion

When a file fails QA more than `escalation.max_retries` times, the Engineer:
1. **Deletes the file** from disk.
2. Removes it from the green set in Redis.
3. Resets retry and defer counters.

The PM will see the file as missing in the next gap analysis and create a fresh task, potentially with a different approach.

### 6.2 Defer Loop Cap

When the Engineer defers a task (path B), it re-queues the original task. To prevent infinite deferral loops, the system tracks how many times each task has been deferred. After `agents.engineer.max_defer_requeues` deferrals, the Engineer **forces a completion attempt** instead of deferring again.

### 6.3 PM Stall Detection

The PM tracks the green file count between iterations. If no new green files appear for `fault_tolerance.pm_stall_threshold` consecutive iterations:
1. The PM **flushes all pending** `task`, `fix_request`, and `task_done` queues.
2. Re-runs gap analysis from scratch based on what is actually green.

This breaks deadlocks caused by tasks stuck in retry loops or signals that will never be consumed.

### 6.4 LLM Retry with Backoff

All Gemini API calls retry up to `gemini.llm_retries` times with exponential backoff (`backoff^attempt` seconds). This handles transient failures: rate limits, timeouts, and network errors.

---

## 7. Configuration Philosophy

All numeric constants and thresholds live in `config.yaml` so they can be tuned without code changes. This includes:

| Config key | Default | Purpose |
|---|---|---|
| `gemini.llm_retries` | 3 | Max LLM API call retries |
| `gemini.llm_retry_backoff` | 2.0 | Exponential backoff base (seconds) |
| `gemini.max_concurrent_llm_calls` | 10 | Semaphore limit for parallel API calls |
| `agents.pm.max_tasks_per_iteration` | 3 | Max tasks the PM creates per gap analysis |
| `agents.engineer.max_defer_requeues` | 3 | Max times a task can be deferred before forcing |
| `escalation.max_retries` | 3 | QA fix attempts before deleting the file |
| `fault_tolerance.pm_stall_threshold` | 3 | Iterations with no progress before queue flush |
| `workers.engineers` | 3 | Parallel Engineer threads |
| `workers.qa_engineers` | 1 | Parallel QA threads |

---

## 8. Agent Lifecycle Management

The lifecycle of agents — spawning and dissolving — is managed purely by the presence of signals in Redis.

### 8.1 Creation and Activation

- **Task Availability:** An Engineer is activated when a `task` or `fix_request` signal appears in Redis.
- **Validation Needs:** A QA Engineer is activated when a `task_done` signal appears.
- **Continuous Planning:** The PM runs in a continuous loop, sleeping while waiting for files to reach `green` status.

### 8.2 Destruction and Deactivation (Signal Decay)

- **Task Depletion:** Once a signal is consumed, it is removed from Redis. When no signals remain, the contractor agents (Engineers and QA) dissolve or return to an idle pool.
- **Project Completion:** When the PM's gap analysis returns zero missing features, the PM loop terminates.

---

## 9. Advanced Techniques

### 9.1 Mixture of Agents (MoA) — Parallel Contractors

Because Engineers do not plan or depend on each other for task assignment, they function as an embarrassingly parallel workforce. Multiple Engineers can claim different `task` signals simultaneously, writing independent code files concurrently.

### 9.2 Executable Feedback Loop (MetaGPT-style)

Actual runtime errors act as stigmergic triggers, preventing hallucinated fixes.

1. **Execution:** The QA Engineer physically executes tests.
2. **Error Signal:** On failure, QA captures the stack trace in a `fix_request` signal.
3. **Self-Correction:** The Engineer uses the explicit failure details to fix the code, repeating until tests pass.

---

## 10. Design Advantages

- **Acyclic Layered Dependencies:** Forcing code into `layer_1`, `layer_2`, etc. based on dependencies guarantees a strict, bottom-up DAG (Directed Acyclic Graph), preventing circular imports and making the system naturally easier to test.
- **Atomic Task Claiming:** Redis allows Engineers to safely use `SETNX` (or similar locking) to claim tasks without race conditions.
- **Low Overhead:** Moving coordination out of the file system into memory drastically reduces I/O overhead.
- **Typed Communication:** A strict set of 4 signals keeps agent interaction predictable and auditable.
- **No Infinite Chat Loops:** Communication relies purely on structured signals, bypassing cascading hallucinations and conversational loops.
- **Executable Verification:** The QA Engineer provides concrete, executable feedback (runtime errors and test results) rather than subjective code review.
- **Incremental Planning:** The PM re-evaluates the plan only based on verified (`green`) code, ensuring the project is built on solid foundations step-by-step.