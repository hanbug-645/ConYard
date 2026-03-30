# System Design: Hierarchical Stigmergy

## 1. The Environment

Instead of a single message pool, the environment is a **nested directory tree**. This mirrors Crosscutting Hierarchical Interaction found in Complex Adaptive Systems, where systems have many levels of organization and units at lower levels serve as "building blocks" for higher levels.

- **Pheromones (Artifacts):** Instead of a single `readme.md`, every directory contains a **standard file set** (the "manifest") that collectively describes its state:

  | File | Purpose |
  |---|---|
  | `prd.md` | Requirements for this directory's scope |
  | `manifest.json` | Lists every expected deliverable (sub-dirs, code files) with its current status: `pending`, `in_progress`, `pass`, `fail`, `blocked` |
  | `review.md` | Reviewer feedback on failing code |
  | `escalation.md` | Created when local failures exceed a threshold; signals upward to the parent directory |
  | `vote_result.json` | Created by the Voter after evaluating competing parallel approaches (see §3.4) |
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
  - **DEBUG mode:** Finds project by identifier, delegates technical analysis to Debugger agent, displays results.
  - **README generation:** After pipeline completion, generates comprehensive README with entry points and setup instructions.
- **Scope:** Communication only. Does **not** perform technical analysis, code generation, or debugging — those belong to specialized agents.

### B. Architect (Decomposition)

- **Goal:** Decompose a high-level PRD into sub-components by creating directory structure.
- **Trigger:** A directory contains a `prd.md` but no sub-directories, no code files, and no `manifest.json`.
- **Action:** Reads `prd.md`, creates sub-directories (e.g., `/frontend`, `/backend`, `/database`), and initializes each with a skeletal `prd.md` **and** a `manifest.json` listing expected deliverables as `pending`. Updates its own `manifest.json` to track the new children.
- **Scope:** Pure structural decomposition only. Creates FLAT, WIDE directory structures (siblings, not nested). Does **not** handle re-planning, risk assessment, or root structure — those belong to Manager and Debugger.

### C. Debugger (Technical Analysis)

- **Goal:** Assess risk, manage escalation responses, analyze issues, and fix problematic code.
- **Trigger (escalation):** An `escalation.md` appears in a child directory, OR a child's status in the local `manifest.json` is `blocked`. This is the **upward feedback loop** — the Debugger restructures the plan after implementation hits a wall (see §3.3).
- **Trigger (risk):** After the Architect creates initial structure, the Debugger reviews the `manifest.json` and flags high-risk deliverables with `risk: "high"`.
- **Trigger (DEBUG):** Called directly by Manager with `analyze_and_fix()` for user-reported issues.
- **Actions:**
  - **Analyze issues:** Identifies problematic files using LLM analysis based on user instructions or error patterns.
  - **Fix code:** Creates escalation, executes fixes, cleans up after completion.
  - **Re-plan:** On escalation, can restructure, re-route, or further escalate (see §3.3).
  - **Adjust constraints:** Can issue a `change_request.md` to the PM to simplify or redirect a sub-directory's PRD.
- **Scope:** Technical problem-solving only. Does **not** handle user communication (Manager) or regular code writing (Engineer).

### D. Product Manager (PM) (Requirements)

- **Goal:** Refine requirements and define file deliverables for subdirectories.
- **Trigger:** A sub-directory where `manifest.json` exists and all deliverables are `pending` (i.e., just initialized), OR a `change_request.md` from the Debugger or a higher level.
- **Action:** Expands the skeletal `prd.md` into a detailed, scoped PRD and updates `manifest.json` entries with concrete file names (in `lib/` folder) and descriptions. For change requests, modifies the existing `prd.md` and `manifest.json` to reflect new constraints.
- **Scope:** Works ONLY on subdirectories. Root structure is defined by Manager. All files go in `lib/` folder, tests in `lib/test/`.

### E. Engineer (Implementation)

- **Goal:** Implement the requirements of a specific layer.
- **Trigger:** `manifest.json` at a leaf node lists code deliverables with status `pending` (or `fail` after a review cycle).
- **Action:** Writes source code as specified by the local `prd.md`, deposits it into the directory (creating parent directories as needed), and updates the deliverable's status to `in_progress` in `manifest.json`. Writes both implementation and test files.
- **Scope:** Code implementation only. Does **not** define what files to create (PM) or review quality (Reviewer) or fix bugs (Debugger).

### F. Code Reviewer / QA (Quality Review)

- **Goal:** Ensure code meets the local PRD requirements.
- **Trigger:** A deliverable in `manifest.json` has status `in_progress` and the corresponding file exists (checks both direct path and `lib/` subdirectory).
- **Action:** Compares the code against the local `prd.md` and verifies quality (small, focused, <100 lines).
  - **On pass:** Updates the deliverable's status to `pass` in `manifest.json`. If *all* deliverables are `pass`, creates `status_pass.flag`.
  - **On fail:** Updates status to `fail`, writes `review.md`. If failures for a deliverable exceed a retry threshold, writes `escalation.md` to trigger upward feedback.
- **Scope:** Quality verification only. Does **not** write or fix code (Engineer/Debugger) or define requirements (PM).

### F. Voter

- **Goal:** Evaluate competing parallel approaches and select the best one.
- **Trigger:** A `manifest.json` entry with `mode: "parallel"` where at least one candidate has `status_pass.flag`, OR all candidates have terminated (pass or blocked).
- **Evaluation criteria:**
  1. **Correctness** — Did it pass all tests?
  2. **Code quality** — Readability, maintainability, adherence to PRD.
  3. **Performance** — Runtime/resource efficiency (if benchmarks exist).
  4. **Simplicity** — Fewer lines, fewer dependencies preferred.
- **Action:** Reads the code and test results from each passing candidate, scores them, and writes `vote_result.json` in the parent directory with the ranking and rationale. Promotes the winner and prunes losers (see §3.4).

---

## 3. Execution Flow (Emergent Behavior)

Control propagates both top-down and bottom-up, allowing the system to self-organize and adapt.

### 3.1 Top-Down Delegation

**Server Mode:** User sends `DO build a snake game in js` → Manager creates initial `prd.md` and root manifest with entry point files (e.g., `index.html`). Pipeline runs in background.

**Pipeline:** The Architect creates `/ui` and `/logic` folders, each with a skeletal `prd.md` and a `manifest.json`. The Debugger reviews for risk flags. The PM expands the PRDs and populates the manifests with `lib/` files. The Engineer reads the leaf-node PRDs, writes `lib/render.js` in `/ui` and `lib/engine.js` in `/logic`, and marks them `in_progress` in the local manifests. Reviewer verifies quality.

### 3.2 Pending-Task Detection

An agent at any level can determine remaining work by reading `manifest.json`:

```
/project/manifest.json
├── ui/       → status: "in_progress"  (1/2 deliverables pass)
└── logic/    → status: "pass"
```

The parent manifest **rolls up** child statuses automatically. A directory is `pass` only when every deliverable (and every child directory) in its manifest is `pass`. This means the root `/project/manifest.json` gives a single, authoritative view of overall progress — no agent needs to recursively walk the tree.

### 3.3 Upward Escalation

When implementation hits a wall that local retries cannot fix, the feedback loop **propagates upward** rather than looping forever at the leaf:

1. **Local retry (Engineer ↔ Reviewer):** The Engineer retries based on `review.md`. This is the fast, local loop.
2. **PM intervention:** If a deliverable's fail count exceeds a threshold (tracked in `manifest.json`), the PM is triggered to simplify the local `prd.md`.
3. **Escalation:** If the PM's simplification still fails, or if the failure is structural (e.g., a dependency between sibling directories is impossible), the Reviewer writes `escalation.md` in the failing directory. This file includes:
   - The original requirement that cannot be met
   - A summary of attempted fixes and why they failed
   - A suggested re-decomposition or constraint change
4. **Debugger re-plan:** The parent directory's Debugger detects `escalation.md` (or sees `blocked` status in its `manifest.json`). It can now:
   - **Restructure:** Delete/replace the blocked sub-directory and have the Architect create a new decomposition.
   - **Re-route:** Merge responsibilities into a sibling directory.
   - **Adjust constraints:** Issue a `change_request.md` to PM to simplify requirements.
   - **Escalate further:** If the Debugger at this level cannot resolve it, it writes its own `escalation.md`, propagating the signal to *its* parent. This recursive escalation continues until the problem reaches a level with enough authority to resolve it.

**User-Initiated Debug:** User can also trigger debugging via `DEBUG <project_id> <instructions>` command. Manager finds the project, Debugger analyzes files, identifies issues, and fixes problematic code.

### 3.4 Redundant Parallel Approaches and Voting

Inspired by ant colonies where multiple foragers explore redundant paths to cover failure, the Debugger can launch **parallel competing approaches** for any key step. This trades compute cost for resilience.

#### Spawning (Debugger)

When the Debugger identifies a component as high-risk (ambiguous requirements, unknown feasibility, or after a first-attempt escalation), it creates N sibling directories for the same deliverable:

```
/project/backend/
├── manifest.json          → auth: { mode: "parallel", candidates: ["auth_A", "auth_B", "auth_C"] }
├── auth_A/                → approach: session-based, temperature: 0.3
├── auth_B/                → approach: JWT-based, temperature: 0.7
└── auth_C/                → approach: OAuth-wrapper, temperature: 1.0
```

Each candidate directory is a **fully independent branch** — it gets its own `prd.md`, `manifest.json`, and runs through the normal PM → Engineer → QA pipeline in parallel. The Debugger can vary:
- **Strategy:** Different architectural approaches to the same requirement.
- **Temperature:** Same prompt but different LLM sampling temperatures for diversity.
- **Agent pool:** Different model configurations or specialized agents.

#### Voting and Pruning (Voter)

Once candidates finish, the Voter is triggered (see §2.F for criteria). After scoring:
1. The **winning** candidate directory is promoted — renamed to the canonical name (e.g., `/auth_A/` → `/auth/`) and its status in the parent `manifest.json` is set to `pass`.
2. **Losing** candidate directories are archived or deleted. Their `manifest.json` entries are removed.
3. If **no candidate passes**, this counts as a structural failure and triggers escalation (§3.3) — the Debugger re-plans the requirement.

#### When to Use Parallel Approaches

Not every step warrants redundancy. The Debugger spawns parallel candidates when:
- The PRD is ambiguous and multiple valid interpretations exist.
- A previous single attempt escalated (§3.3) — retry with diversity.
- The component is on the critical path and failure cost is high.
- The parent `manifest.json` explicitly flags a deliverable as `risk: "high"`.

### 3.5 Bottom-Up Adaptation (Graceful Degradation)

If failures accumulate at a leaf (a "quantitative stigmergic signal" visible in `manifest.json` fail counts), the PM simplifies the local `prd.md` requirements to something achievable. If that still fails, escalation kicks in (§3.3), which may trigger a redundant parallel retry (§3.4).

---

## 4. Agent Lifecycle Management

The lifecycle of agents — spawning and dissolving — is **not** managed by a rigid top-down controller. Agents dynamically form, dissolve, and reorganize in response to tasks and environmental cues.

### 4.1 Creation and Activation

- **Qualitative Triggers ("Missing File"):** An agent is activated when a specific structural void appears. A `manifest.json` entry with status `pending` and no corresponding file triggers the Engineer's SOP.
- **Quantitative Triggers ("Pheromone Gradient"):** If a directory's `manifest.json` shows many `pending` or `fail` entries, this concentration acts as a digital pheromone, signaling the orchestration layer to allocate more concurrent Engineer agents to that branch.
- **Peer Delegation (A2A Protocol):** Agents can use Agent-to-Agent protocols to directly negotiate and delegate subtasks. An Architect or Strategist can spawn a temporary helper agent for a newly discovered sub-requirement without centralized intervention.

### 4.2 Destruction and Deactivation (Signal Decay)

Agents are destroyed (or returned to an idle pool) when the environmental signals that sustain them disappear.

- **Task Depletion:** Once all entries in `manifest.json` reach `pass` and `status_pass.flag` is created, the "work needed" signal vanishes. Agents dissolve their current state and return to polling for new tasks.
- **Avoiding Over-Constrained Splintering:** If constraints become unsatisfiable (e.g., conflicting PRD requirements), the escalation mechanism (§3.3) propagates the problem upward. The Strategist restructures the plan, effectively killing the old task and spawning a new, achievable one.
- **Resource Management:** An execution and control management unit in the orchestration layer tracks workflow lifecycles, ensuring that once an agent's role is completed and validated, its resources are terminated to balance throughput and cost.

By tying agent existence directly to unfinished artifacts, the system naturally cleans up after itself.

---

## 5. Advanced Techniques

### 5.1 Mixture of Agents (MoA) — Parallel File Proposals

In the MoA framework, LLMs are separated into **Proposers** (generating diverse outputs) and **Aggregators** (synthesizing them into a single high-quality result).

- **Proposer Trigger:** When a leaf-node `prd.md` is finalized, multiple Engineer agents are triggered simultaneously. They deposit competing candidate files (e.g., `logic_candidate_A.js`, `logic_candidate_B.js`, `logic_candidate_C.js`).
- **Aggregator Trigger:** An Aggregator Engineer polls the directory. Its trigger is the presence of multiple `_candidate.js` files. It synthesizes their best approaches into the final, authoritative `logic.js`.

### 5.2 Tree of Thoughts (ToT) — Directory Branching and Pruning

ToT frames problem-solving as a search over a tree where each node is a partial solution. The hierarchical file system is already a tree, making it a natural physical representation. The **redundant parallel approach** mechanism (§3.4) is the concrete implementation of ToT in this system:

- **Branches as Thoughts:** Parallel candidate directories (e.g., `/auth_A`, `/auth_B`) are the "thought states."
- **State Evaluation:** The Voter (§2.F) functions as the state evaluator, scoring candidates via `vote_result.json`.
- **Routing and Backtracking:** Pruning losing candidates is backtracking. If no candidate passes, the system backtracks further via escalation (§3.3), and the Strategist may re-plan and launch a new round of parallel branches.

### 5.3 Executable Feedback Loop (MetaGPT-style)

Actual runtime errors act as stigmergic triggers, preventing hallucinated fixes.

1. **Test Generation:** The Engineer's SOP requires writing a corresponding test file (e.g., `test_logic.js`) alongside `logic.js`.
2. **Execution as Stigmergy:** The QA agent physically executes the tests in a secure sandbox.
3. **Error Log Trigger:** On failure, the exact runtime stack trace is deposited as `execution_errors.log`.
4. **Self-Correction Loop:** The Engineer observes `execution_errors.log` alongside its code, triggering its debugging SOP. It reads its past code and the concrete error log, then overwrites the file with a new attempt. This repeats until tests pass and `status_pass.flag` is created.

---

## 6. Design Advantages

- **Mission Command:** Delegating control down the file tree grants lower-level units the leeway to adapt to local conditions and shortens feedback loops.
- **Scale-Free Complexity:** The same dynamics repeat at every scale — the logic governing `/project` is identical to that governing `/project/backend/auth/utils`.
- **No Infinite Loops:** Communication relies purely on structured artifacts rather than open-ended chatting, bypassing cascading hallucinations and dialogue loops.
- **Self-Cleaning:** Agent existence is tied to unfinished work; when the work is done, signals decay and agents dissolve.
- **Redundancy for Resilience:** Like ant colonies sending multiple foragers down parallel paths, the Strategist can spawn competing approaches for high-risk steps. The Voter selects the best; failure of one branch does not block progress.
- **Resilient Search Tree:** Combining ToT (architecture exploration), MoA (diverse implementations), redundant approaches (parallel candidates + voting), and executable feedback (strict verification) transforms the file system into a self-correcting search tree.