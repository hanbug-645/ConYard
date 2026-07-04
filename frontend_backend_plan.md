# MVP Design: Conversational Template-to-Playable Game

_Temp scratch doc — delete or fold into `PRD.md` once agreed._

## Product goal

Build the simplest first version of ConYard that proves the real product loop:

1. User gives a rough game idea or a requested change.
2. Backend uses an LLM to choose the best installed template.
3. Backend asks one short clarification question if key template-specific
   information is missing.
4. Backend generates or updates one template subclass file.
5. Frontend renders the playable game immediately.
6. User can keep giving feedback, and the backend iterates on the current game.

The important MVP behavior is not just first generation. It is the interaction:
route → clarify if needed → generate → render → revise.

---

## MVP scope

**Out of scope for v1:** streaming responses, server-side sessions/DB,
code editor tab, logs tab, rollback, manual template picker, auth,
self-healing runtime-error loops, Sandpack (unless the plain iframe
renderer proves inadequate).

---

## 1. User interaction model

The frontend should feel like a simple conversation, not a one-shot form.

### First user turn

User might say something vague:

```text
make me a cute food collecting game
```

Backend does not blindly generate Snake. It first asks the LLM to match the
request against installed templates and decide whether enough information exists
to generate a good first version.

Possible backend outcomes:

1. **Clarification needed**
   - Example: "I can make this as a Snake-style collecting game. What should the
     collectible look like — fruit, coins, stars, or something else?"
2. **Generate now**
   - Example: prompt clearly maps to Snake and includes enough customization.
3. **Unsupported / redirect**
   - Example: user asks for a 3D racing game and no matching template exists.
     Backend should offer the closest supported template instead of pretending.

### Clarification turn

If the backend asked a question, the next user message answers it:

```text
strawberries, and make the snake pink
```

Backend combines:

- original prompt,
- selected template,
- clarification question,
- user's answer,
- template `HOOKS`,
- relevant examples,

then generates the game.

### Iteration turn

After the game renders, user can say:

```text
make it faster and change the walls to wrap around
```

Backend should treat this as an edit to the current game, not a brand new game.
It receives the current `template_id`, current `generated_code`, and recent
conversation state from the frontend, then asks the LLM to return a revised
`game.js`.

---

## 2. API contract

One turn-based endpoint. Backend is stateless; frontend echoes state
back each turn.

### `POST /game-turn`

Request:

```json
{
  "message": "make me a cute food collecting game",
  "state": {
    "template_id": null,
    "phase": "new",
    "summary": "",
    "pending_question": null,
    "generated_code": null,
    "recent_messages": [
      { "role": "user", "text": "..." },
      { "role": "assistant", "text": "..." }
    ]
  }
}
```

`recent_messages` is the last N (e.g. 6) turns. It supplements `summary`
for edit turns where the model needs the actual phrasing of prior
feedback. `phase` ∈ `"new" | "awaiting_clarification" | "ready"`.

**Response envelope (all types):**

```json
{
  "type": "question" | "game" | "message",
  "message": "assistant-facing text",
  "html": "...only when type=game...",
  "generated_code": "...only when type=game...",
  "state": { /* updated state, always returned */ }
}
```

Type-specific rules:

- **`question`** — `state.phase = "awaiting_clarification"`,
  `state.pending_question` set, no `html`.
- **`game`** — `state.phase = "ready"`, `state.generated_code` and
  response `html` populated.
- **`message`** — informational (e.g. "unsupported request"); no `html`,
  no state change beyond `summary`.

Errors return HTTP 4xx/5xx with `{ "detail": "..." }`. No debug or
token-count fields in v1.

---

## 3. Backend design

### Files to change

- `backend/main.py`
- `backend/Dockerfile`
- Optional: `backend/game_generator.py` if `main.py` becomes too large.

Do not add new engine modules for v1 unless needed.

### Backend turn flow

Each `/game-turn` request runs a small decision pipeline.

#### Step A — Build template registry

The planning call sees a compact JSON registry, not raw template files:

```json
[
  {
    "id": "snake",
    "name": "Snake",
    "description": "...from manifest...",
    "routing_keywords": ["snake", "grid", "food", ...],
    "hook_names": ["getGameTitle", "getFoodShape", "getWallMode", ...]
  }
]
```

Full `HOOKS` details and example files are loaded only for the template
the planning call selects, and only for `generate`/`edit` calls. This
keeps the planning prompt small.

#### Step B — Planning LLM call

Ask Gemini for a strict JSON decision. Use Gemini's structured output
(`response_mime_type="application/json"` with a schema) to avoid parsing
issues:

```json
{
  "action": "ask" | "generate" | "edit" | "unsupported",
  "template_id": "snake" | null,
  "question": "...only if action is ask...",
  "summary": "updated conversation summary"
}
```

Planning input:

- current user message,
- current `state` (including `recent_messages`),
- template registry from Step A.

Rules the planning prompt encodes:

- If `state.generated_code` exists, prefer `edit` unless the user clearly
  asks for a new game.
- If key template-specific info is missing, choose `ask` and set one
  question.
- Ask at most one clarification per turn.
- Do not ask for optional details when sensible defaults exist.
- If no installed template fits, choose `unsupported` and suggest the
  closest available template in `summary`.

#### Step C — If action is `ask`

Return a `type: "question"` response immediately. Do not generate code yet.

#### Step D — If action is `generate`

Call Gemini again to generate one `game.js` subclass for the selected template.

Generation prompt includes:

- selected template id,
- `HOOKS` block from `base.js`,
- 2-4 relevant example files,
- current conversation summary,
- latest user message,
- any answered clarification.

The generated file must:

- import from `./base.js`,
- extend `SnakeGame`,
- override only methods listed in `HOOKS`,
- call `mount(CustomGame)` at the bottom,
- return JavaScript only, no Markdown fences.

#### Step E — If action is `edit`

Call Gemini to rewrite the existing `generated_code` rather than creating a new
file from scratch.

Edit prompt includes:

- current `generated_code`,
- selected template `HOOKS`,
- latest user feedback,
- conversation summary,
- relevant examples if useful.

The output is still a complete replacement `game.js`, not a patch. That keeps v1
simple.

#### Step F — Minimal validation

Determine the expected base class name from the template's manifest.
The current `manifest.json` does not carry this yet, so add a
`"base_class"` field (e.g. `"SnakeGame"`) as part of Step 4. Validate
the generated code:

- contains `import { <BaseClass>, mount } from "./base.js"`,
- contains `extends <BaseClass>`,
- contains `mount(`,
- does not import from `dep/`,
- does not contain Markdown fences.

If validation fails in v1, return a friendly `type: "message"` response
asking the user to retry. Add automatic retry later.

#### Step G — Build playable HTML

Inputs used from the template bundle:

- `dep/styles.css`,
- `dep/engine.js`,
- `base.js`.

`manifest.json` and `example/` are **not** shipped to the browser.

Assemble one self-contained HTML document:

- inline `dep/styles.css` in a `<style>` tag,
- flatten the three JS files into one inline `<script type="module">`
  in order: engine → base → game,
- strip `export` keywords from `dep/engine.js`,
- strip `import`/`export` lines from `base.js`,
- strip the `import ... from "./base.js"` line from generated `game.js`,
- keep the generated `mount(CustomGame)` call at the end.

Return `{ type: "game", message, html, generated_code, state }`. This
avoids relative-import problems inside `iframe.srcDoc`.

### LLM call count per turn

| Situation | Calls |
|---|---|
| Vague request needing clarification | 1 (plan only) |
| Clear first request | 2 (plan + generate) |
| Answering a clarification | 2 (plan + generate) |
| Feedback on existing game | 2 (plan + edit) |
| Unsupported request | 1 (plan only) |

---

## 4. Frontend design

### Files to change

- `frontend/app/page.tsx`
- Optional later split:
  - `frontend/app/components/ConversationPanel.tsx`
  - `frontend/app/components/GameFrame.tsx`
  - `frontend/app/lib/api.ts`

For v1, it is acceptable to keep the page in one file if it remains readable.

### UI layout

Simple two-panel layout:

```text
┌──────────────────────────────┬──────────────────────────────────┐
│ Conversation                  │ Game Renderer                    │
│                              │                                  │
│ assistant/user messages       │ [iframe showing generated game]  │
│                              │                                  │
│ [textarea]                    │                                  │
│ [Send]                        │                                  │
│ status/error                  │                                  │
└──────────────────────────────┴──────────────────────────────────┘
```

### Frontend state

Keep state in React memory only (Zustand is already installed):

```ts
type Message = { role: "user" | "assistant"; text: string };

type GameTurnState = {
  template_id: string | null;
  phase: "new" | "awaiting_clarification" | "ready";
  summary: string;
  pending_question: string | null;
  generated_code: string | null;
  recent_messages: Message[]; // last 6, sent with each turn
};
```

Also keep a full `messages[]` for display. Refresh discards state in v1.

### Frontend flow

1. User submits a message; append it to `messages` and `recent_messages`.
2. Frontend `POST`s `{ message, state }` to `/game-turn`.
3. On success:
   - `question` → append assistant text; update state; iframe unchanged.
   - `game` → append assistant text; update state; set `iframe.srcDoc = html`.
   - `message` → append assistant text; update state; iframe unchanged.
4. On failure: show the backend `detail` inline; do not touch state.

**Concurrency:** disable the send button while a turn is in flight. If a
request is aborted, discard its response.

**Empty state:** before the first `game` response, the right pane shows
a short placeholder ("Your game will appear here after your first
request.").

### Iframe renderer

Use `<iframe srcDoc={html} sandbox="allow-scripts" />`. This avoids
Sandpack, Blob URLs, and server-side preview storage. `allow-scripts`
without `allow-same-origin` is enough for the game to run and prevents
the iframe from touching the parent app.

---

## 5. Engine usage

Use the existing engine structure as-is:

- `TemplateManager` / manifests provide installed template inventory.
- `Template.bundle_files` provides `base.js`, `dep/engine.js`, and
  `dep/styles.css`.
- `base.js` provides the `HOOKS` contract.
- `example/` provides few-shot references.

Do not refactor `engine/check_examples.py` before the first conversational loop
works.
Do not add `engine/hooks.py` or `engine/bundler.py` yet.

The only acceptable engine change during v1 is a small fix if the backend cannot
reliably read template files.

---

## 6. Implementation order

Each step ends with a runnable outcome. Do not start step N+1 until N
works end-to-end.

### Step 1 — Backend static turn stub

- Add `POST /game-turn` in `backend/main.py`.
- Wire the engine path so `TemplateManager` loads.
- Ignore Gemini. Hardcoded logic:
  - if `state.phase == "new"` and message is short/vague → return a
    `question` response,
  - otherwise → return a `game` response whose HTML is the unmodified
    default Snake bundle (assembled from `bundle_files`).
- **Runnable:** curl the endpoint, get a valid response of each type.

### Step 2 — Frontend conversation + iframe

- Replace `frontend/app/page.tsx` with the two-panel layout.
- Implement `messages[]`, `state`, send-button disable, iframe `srcDoc`
  with sandbox.
- **Runnable:** browser shows conversation → question → answer →
  default Snake playable in the iframe.

### Step 3 — Planning LLM call

- Replace the stub decision in Step 1 with a Gemini structured-JSON
  planning call.
- Load and pass the template registry (Step A).
- Enforce planning rules on the prompt.
- **Runnable:** vague prompts → clarification; clear prompts → still
  return the default bundle (no real generation yet).

### Step 4 — Generation LLM call

- On `action=generate`, call Gemini with the selected template's `HOOKS`
  and 2–4 example files.
- Add validation (Step F).
- Assemble the HTML using Step G.
- **Runnable:** "pink snake with wrap walls" renders a customized game.

### Step 5 — Edit LLM call

- On `action=edit`, feed current `generated_code` plus `recent_messages`
  to Gemini and expect a full replacement `game.js`.
- **Runnable:** after a game renders, "make it faster" produces an
  updated playable game.

### Step 6 — Docker/dev polish

- Update `backend/Dockerfile` to copy `engine/`.
- Confirm env vars: `NEXT_PUBLIC_API_URL`, `GCP_PROJECT_ID`,
  `GCP_LOCATION`.
- Add a short README section on running both services locally.

---

## 7. Appendix

### Backend import path

- Local dev: run backend from repo root or `sys.path.insert` in
  `backend/main.py` to find `engine/`.
- Docker: `backend/Dockerfile` must `COPY` both `backend/` and `engine/`.
- Do not package the repo as an installable Python project in v1.

### Deferred to later iterations

Streaming responses, server-side sessions, code tab, logs tab, Sandpack,
automatic retry on validation failure, hook-parsing helper in engine,
validation-helper refactor, manual template picker, saving generated
games, runtime-error "Fix It" loop, rollback/time-machine.

### v1 done when

1. Vague prompt → clarification question.
2. Clarification answered → playable game in the iframe.
3. Follow-up feedback → updated playable game.
4. Unsupported request → clear message, no crash.
5. Failure paths surface `detail` inline; no silent errors.
