# System Design: Hierarchical Stigmergy

## 1. The Environment

Instead of a single message pool, the environment is a **nested directory tree**. This mirrors Crosscutting Hierarchical Interaction found in Complex Adaptive Systems, where systems have many levels of organization and units at lower levels serve as "building blocks" for higher levels.

- **Pheromones (Artifacts):** Instead of a single `readme.md`, every directory contains a **standard file set** (the "manifest") that collectively describes its state:

  | File | Purpose |
  |---|---|
  | `prd.md` | Requirements for this directory's scope |
  | `manifest.json` | Lists every expected deliverable (sub-dirs, code files) with its current status: `pending`, `in_progress`, `pass`, `fail`, `blocked` |
  | `review.md` | QA Engineer feedback on failing code |
  | `error_trace.md` | Structured error log deposited by the Diagnostic Agent after runtime failure |
  | `escalation.md` | Created when local failures exceed a threshold; signals upward to the parent directory |
  | `change_request.md` | Created by the Healing Agent to simplify or redirect a sub-directory's PRD |
  | `status_pass.flag` | Created when all items in `manifest.json` reach `pass` |

  Additional stimuli include code files (`.py`, `.js`), test files, and `execution_errors.log`.

- **Pending-Task Visibility:** Any agent can read `manifest.json` to determine whether a sub-directory still has pending work. A parent directory's manifest **aggregates** the status of its children — if `/project/backend/auth/` is still `in_progress`, then `/project/backend/manifest.json` reflects that. This gives every level of the tree full visibility into the completion state below it without centralized bookkeeping.

- **Decentralized Coordination:** Modifications made to the environment feed back to organize collective behavior without a central controller. Agents continuously poll the file system tree, and their actions are triggered strictly by the local manifest state of a specific directory layer.

---

## 2. Agent Roles and Stigmergic Triggers (SOPs)

LLM agents observe local directory states and execute specific tasks based on their assigned roles, analogous to wasps using lookup tables of "microrules."

### A. Manager (Communication Layer)

- **Goal:** Interface between user and technical agents. Handle user communication and coordinate agent activities.
- **Trigger:** Called directly by server for user commands (DO, ASK, DEBUG).
- **Actions:**
  - **DO mode:** Creates initial PRD from user task, defines root-level file structure (entry points, config files), creates initial manifest.
  - **ASK mode:** Answers user questions using LLM with project context.
  - **DEBUG mode:** Finds project by identifier, delegates technical analysis to Diagnostic Agent, displays results.
  - **README generation:** After pipeline completion, generates comprehensive README with entry points and setup instructions.
- **Scope:** Communication only. Does **not** perform technical analysis, code generation, or debugging — those belong to specialized agents.

### B. Architect (Decomposition)

- **Goal:** Decompose a high-level PRD into sub-components by creating directory structure.
- **Trigger:** A directory contains a `prd.md` but no sub-directories, no code files, and no `manifest.json`.
- **Action:** Reads `prd.md`, creates sub-directories (e.g., `/frontend`, `/backend`, `/database`), and initializes each with a skeletal `prd.md` **and** a `manifest.json` listing expected deliverables as `pending`. Updates its own `manifest.json` to track the new children.
- **Feature Request Trigger:** An updated master PRD (detected via timestamp or diff) triggers the Architect to translate new requirements into system design components, modifying interface definitions and file lists. If the feature requires a new module, the Architect creates a new sub-directory (e.g., `/multiplayer`) and deposits a skeletal `prd.md` inside it.
- **Scope:** Pure structural decomposition only. Creates FLAT, WIDE directory structures (siblings, not nested). Does **not** handle re-planning, risk assessment, or root structure — those belong to Manager and Healing Agent.

### C. Product Manager (PM) (Requirements)

- **Goal:** Refine requirements and define file deliverables for subdirectories.
- **Trigger:** A sub-directory where `manifest.json` exists and all deliverables are `pending` (i.e., just initialized), OR a `change_request.md` from the Healing Agent or a higher level.
- **Feature Request Trigger:** When the root PRD is updated by the user, the PM observes the change, conducts a requirement analysis, and updates the structured Product Requirements Document to include new "User Stories" and a "Requirement Pool."
- **Action:** Expands the skeletal `prd.md` into a detailed, scoped PRD and updates `manifest.json` entries with concrete file names and descriptions. For change requests, modifies the existing `prd.md` and `manifest.json` to reflect new constraints.
- **Scope:** Works ONLY on subdirectories. Root structure is defined by Manager.

### D. Engineer (Implementation)

- **Goal:** Implement the requirements of a specific layer.
- **Trigger (initial):** `manifest.json` at a leaf node lists code deliverables with status `pending`.
- **Trigger (self-correction):** An `error_trace.md` file is deposited in the directory by the Diagnostic Agent after a test failure. The Engineer enters an **iterative programming loop**: it reads its past code, compares it against the local `prd.md`, the `error_trace.md`, and the failing test output, then overwrites the code file with a fix.
- **Action:** Writes source code as specified by the local `prd.md`, deposits it into the directory (creating parent directories as needed), and updates the deliverable's status to `in_progress` in `manifest.json`.
- **Retry Limit:** The self-correction loop continues until tests pass or a maximum retry limit (e.g., 3 retries) is reached. If the limit is hit, the file's status is set to `blocked`, signaling the Healing Agent.
- **Scope:** Code implementation and self-correction only. Does **not** define what files to create (PM/Architect), execute tests (QA Engineer), or prune branches (Healing Agent).

### E. QA Engineer (Quality Assurance)

- **Goal:** Write and execute unit tests for code in a directory, providing executable feedback.
- **Trigger:** A deliverable in `manifest.json` has status `in_progress` and the corresponding code file exists.
- **Action:**
  1. **Test Generation:** Writes corresponding unit test cases for the code file, based on the local `prd.md` requirements.
  2. **Test Execution:** Physically executes the tests in a secure sandbox.
  3. **On pass:** Updates the deliverable's status to `pass` in `manifest.json`. If *all* deliverables are `pass`, creates `status_pass.flag`.
  4. **On fail:** Does **not** communicate directly with the Engineer. Instead, passes the failure information to the Diagnostic Agent for structured error deposition. Updates the deliverable's status to `fail` and writes `review.md` with test results.
- **Scope:** Test writing and execution only. Does **not** write application code (Engineer), analyze errors (Diagnostic Agent), or fix bugs (Engineer self-correction).

### F. Diagnostic Agent (Error Analysis)

- **Goal:** Catch runtime failures and deposit structured error logs as stigmergic signals.
- **Trigger:** A test execution by the QA Engineer fails, OR a runtime error occurs during code execution.
- **Trigger (DEBUG):** Called directly by Manager with `analyze_and_fix()` for user-reported issues.
- **Action:** Analyzes the failure, captures the exact runtime stack trace, error type, and relevant context, then deposits a structured `error_trace.md` directly into the local directory. This file includes:
  - The exact error message and stack trace
  - The failing test case(s)
  - The code file(s) involved
  - A concise diagnostic summary
- **Scope:** Error analysis and structured logging only. The Diagnostic Agent acts as the bridge between test failure and Engineer self-correction — it translates raw failures into actionable error pheromones. Does **not** fix code (Engineer) or prune branches (Healing Agent).

### G. Healing Agent (Recovery & Pruning)

- **Goal:** Prune failing branches and trigger re-planning when local retries are exhausted, implementing graceful degradation.
- **Trigger:** A deliverable's fail count in `manifest.json` exceeds the retry threshold and its status is `blocked`, OR an `escalation.md` appears in a child directory.
- **Actions:**
  - **Prune:** Deletes the failing code and error logs, effectively "pruning" the search tree branch (Tree of Thoughts backtracking).
  - **Re-plan:** Leaves a `change_request.md` flag for the PM or Architect to rewrite the local `prd.md` to simplify the requirements, demonstrating graceful degradation.
  - **Restructure:** Can delete/replace a blocked sub-directory and have the Architect create a new decomposition.
  - **Re-route:** Can merge responsibilities into a sibling directory.
  - **Escalate further:** If the Healing Agent at this level cannot resolve it, it writes its own `escalation.md`, propagating the signal to *its* parent. This recursive escalation continues until the problem reaches a level with enough authority to resolve it.
- **Scope:** Recovery and branch management only. Does **not** write code (Engineer), run tests (QA Engineer), or analyze errors (Diagnostic Agent).

---

## 3. Execution Flow (Emergent Behavior)

Control propagates both top-down and bottom-up, allowing the system to self-organize and adapt.

### 3.1 Top-Down Delegation

**Server Mode:** User sends `DO build a snake game in js` → Manager creates initial `prd.md` and root manifest with entry point files (e.g., `index.html`). Pipeline runs in background.

**Pipeline:** The Architect creates `/ui` and `/logic` folders, each with a skeletal `prd.md` and a `manifest.json`. The PM expands the PRDs and populates the manifests with file deliverables. The Engineer reads the leaf-node PRDs, writes code, and marks them `in_progress` in the local manifests. The QA Engineer writes and executes tests to verify quality.

### 3.2 The Debug Flow (Executable Feedback Loop)

When a bug is introduced, the system relies on an **Executable Feedback Loop**, which acts as a self-correction mechanism during runtime. In a stigmergic environment, errors act as "negative feedback" that counterbalances the positive feedback of code generation.

1. **Code Deposition:** The Engineer agent writes code and deposits it in the directory.
2. **Test Generation:** The presence of a new code file triggers the QA Engineer, who writes and executes corresponding unit test cases for that specific directory layer.
3. **The Error Pheromone:** If the code fails, the QA Engineer does **not** "chat" with the Engineer. Instead, the Diagnostic Agent catches the runtime failure and deposits a structured error log (`error_trace.md`) directly into the local directory.
4. **Self-Correction (Debugging):** The Engineer agent is re-triggered by the presence of `error_trace.md`. It enters an iterative programming loop where it checks its past code, compares it with the local PRD (`prd.md`), the system design, and the failing code. It overwrites the code file with a fix. This iterative testing process continues until the test passes or a maximum retry limit (e.g., 3 retries) is reached.
5. **Backtracking (Tree of Thoughts):** If the maximum retries are hit, the system assumes the current branch is over-constrained (an impossible state). The Healing Agent deletes the failing code and error logs, effectively "pruning" the search tree. It leaves a `change_request.md` flag for the PM or Architect to rewrite the local `prd.md` to simplify the requirements, demonstrating graceful degradation.

### 3.3 The Feature Request Flow

A new feature request represents a new environmental stimulus entering the system from the top down. Because the system uses a **Multiscale Competency Architecture (MCA)** where adaptation takes place at every scale, a feature request smoothly trickles down without breaking the entire codebase.

1. **The Top-Level Stimulus:** The human user provides a one-line requirement or detailed prompt (e.g., "Add a multiplayer mode").
2. **PM Requirement Analysis:** The user's input modifies the root directory's master PRD. The Product Manager observes this change, conducts a requirement analysis, and updates the structured Product Requirements Document to include new "User Stories" and a "Requirement Pool."
3. **Architectural Delegation:** The updated master PRD triggers the Architect. The Architect translates the new requirements into system design components, modifying the interface definitions and file lists. If the feature requires a new module, the Architect creates a new sub-directory (e.g., `/multiplayer`) and deposits a skeletal `prd.md` inside it.
4. **Local Execution:** The creation of the new sub-directory triggers the local PM, Engineer, and QA agents for that specific folder. They operate independently to build the new feature without disrupting the code in the `/ui` or `/logic` folders, treating the new task as a localized, isolated building event.

### 3.4 Pending-Task Detection

An agent at any level can determine remaining work by reading `manifest.json`:

```
/project/manifest.json
├── ui/       → status: "in_progress"  (1/2 deliverables pass)
└── logic/    → status: "pass"
```

The parent manifest **rolls up** child statuses automatically. A directory is `pass` only when every deliverable (and every child directory) in its manifest is `pass`. This means the root `/project/manifest.json` gives a single, authoritative view of overall progress — no agent needs to recursively walk the tree.

### 3.5 Upward Escalation

When implementation hits a wall that local retries cannot fix, the feedback loop **propagates upward** rather than looping forever at the leaf:

1. **Local retry (Engineer ↔ QA Engineer):** The Engineer retries based on `error_trace.md`. This is the fast, local loop (see §3.2).
2. **PM intervention:** If a deliverable's fail count exceeds a threshold (tracked in `manifest.json`), the PM is triggered to simplify the local `prd.md`.
3. **Branch pruning:** If the PM's simplification still fails, or if the failure is structural (e.g., a dependency between sibling directories is impossible), the Healing Agent prunes the branch and writes `escalation.md` in the failing directory. This file includes:
   - The original requirement that cannot be met
   - A summary of attempted fixes and why they failed
   - A suggested re-decomposition or constraint change
4. **Healing Agent re-plan:** The parent directory's Healing Agent detects `escalation.md` (or sees `blocked` status in its `manifest.json`). It can now:
   - **Restructure:** Delete/replace the blocked sub-directory and have the Architect create a new decomposition.
   - **Re-route:** Merge responsibilities into a sibling directory.
   - **Adjust constraints:** Issue a `change_request.md` to PM to simplify requirements.
   - **Escalate further:** If the Healing Agent at this level cannot resolve it, it writes its own `escalation.md`, propagating the signal to *its* parent. This recursive escalation continues until the problem reaches a level with enough authority to resolve it.

**User-Initiated Debug:** User can also trigger debugging via `DEBUG <project_id> <instructions>` command. Manager finds the project, Diagnostic Agent analyzes files, identifies issues, and deposits `error_trace.md` for the Engineer's self-correction loop.

### 3.6 Bottom-Up Adaptation (Graceful Degradation)

If failures accumulate at a leaf (a "quantitative stigmergic signal" visible in `manifest.json` fail counts), the PM simplifies the local `prd.md` requirements to something achievable. If that still fails, the Healing Agent prunes the branch (§3.2 step 5), which may trigger an escalation (§3.5) and re-planning at a higher level.

---

## 4. Agent Lifecycle Management

The lifecycle of agents — spawning and dissolving — is **not** managed by a rigid top-down controller. Agents dynamically form, dissolve, and reorganize in response to tasks and environmental cues.

### 4.1 Creation and Activation

- **Qualitative Triggers ("Missing File"):** An agent is activated when a specific structural void appears. A `manifest.json` entry with status `pending` and no corresponding file triggers the Engineer's SOP. An `error_trace.md` triggers the Engineer's self-correction SOP.
- **Quantitative Triggers ("Pheromone Gradient"):** If a directory's `manifest.json` shows many `pending` or `fail` entries, this concentration acts as a digital pheromone, signaling the orchestration layer to allocate more concurrent Engineer agents to that branch.
- **Peer Delegation (A2A Protocol):** Agents can use Agent-to-Agent protocols to directly negotiate and delegate subtasks. An Architect can spawn a temporary helper agent for a newly discovered sub-requirement without centralized intervention.

### 4.2 Destruction and Deactivation (Signal Decay)

Agents are destroyed (or returned to an idle pool) when the environmental signals that sustain them disappear.

- **Task Depletion:** Once all entries in `manifest.json` reach `pass` and `status_pass.flag` is created, the "work needed" signal vanishes. Agents dissolve their current state and return to polling for new tasks.
- **Branch Pruning:** When the Healing Agent prunes a failing branch, it effectively kills the task and all associated agent activity. The Healing Agent restructures the plan via `change_request.md`, spawning a new, achievable task in its place.
- **Resource Management:** An execution and control management unit in the orchestration layer tracks workflow lifecycles, ensuring that once an agent's role is completed and validated, its resources are terminated to balance throughput and cost.

By tying agent existence directly to unfinished artifacts, the system naturally cleans up after itself.

---

## 5. Advanced Techniques

### 5.1 Mixture of Agents (MoA) — Parallel File Proposals

In the MoA framework, LLMs are separated into **Proposers** (generating diverse outputs) and **Aggregators** (synthesizing them into a single high-quality result).

- **Proposer Trigger:** When a leaf-node `prd.md` is finalized, multiple Engineer agents are triggered simultaneously. They deposit competing candidate files (e.g., `logic_candidate_A.js`, `logic_candidate_B.js`, `logic_candidate_C.js`).
- **Aggregator Trigger:** An Aggregator Engineer polls the directory. Its trigger is the presence of multiple `_candidate.js` files. It synthesizes their best approaches into the final, authoritative `logic.js`.

### 5.2 Tree of Thoughts (ToT) — Directory Branching and Pruning

ToT frames problem-solving as a search over a tree where each node is a partial solution. The hierarchical file system is already a tree, making it a natural physical representation.

- **Branches as Thoughts:** Sub-directories created by the Architect represent "thought states" — different decomposition paths.
- **State Evaluation:** The QA Engineer functions as the state evaluator, verifying whether a branch produces working code via executable tests.
- **Backtracking:** When the Healing Agent prunes a failing branch (§3.2 step 5), this is explicit backtracking. The system "rolls back" to the parent level, where the Architect or PM can propose a new decomposition — a new thought branch.
- **Graceful Degradation:** If no decomposition succeeds, the Healing Agent escalates (§3.5), and the PM simplifies requirements. This is analogous to ToT's "beam search with pruning" — the system narrows its search to achievable solutions rather than failing completely.

### 5.3 Executable Feedback Loop (MetaGPT-style)

Actual runtime errors act as stigmergic triggers, preventing hallucinated fixes.

1. **Test Generation:** The QA Engineer writes a corresponding test file (e.g., `test_logic.js`) alongside `logic.js`.
2. **Execution as Stigmergy:** The QA Engineer physically executes the tests in a secure sandbox.
3. **Error Pheromone:** On failure, the Diagnostic Agent captures the exact runtime stack trace and deposits it as `error_trace.md`.
4. **Self-Correction Loop:** The Engineer observes `error_trace.md` alongside its code, triggering its self-correction SOP. It reads its past code and the concrete error log, then overwrites the file with a new attempt. This repeats until tests pass and `status_pass.flag` is created.
5. **Pruning on Failure:** If the self-correction loop exhausts its retry limit, the Healing Agent prunes the branch and escalates (§3.5).

---

## 6. Design Advantages

- **Mission Command:** Delegating control down the file tree grants lower-level units the leeway to adapt to local conditions and shortens feedback loops.
- **Scale-Free Complexity:** The same dynamics repeat at every scale — the logic governing `/project` is identical to that governing `/project/backend/auth/utils`.
- **No Infinite Loops:** Communication relies purely on structured artifacts rather than open-ended chatting, bypassing cascading hallucinations and dialogue loops. The Diagnostic Agent ensures errors are logged as structured data, not conversational messages.
- **Self-Cleaning:** Agent existence is tied to unfinished work; when the work is done, signals decay and agents dissolve.
- **Executable Verification:** The QA Engineer provides concrete, executable feedback — runtime errors and test results — rather than subjective code review, grounding the system in actual behavior.
- **Graceful Degradation:** The Healing Agent ensures the system never gets stuck in impossible states. Failed branches are pruned, requirements are simplified, and the system converges on achievable solutions.
- **Resilient Search Tree:** Combining ToT (architecture exploration), MoA (diverse implementations), executable feedback (strict verification), and graceful degradation (Healing Agent pruning) transforms the file system into a self-correcting search tree.