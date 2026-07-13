# Template Folder Structure

Every game template under `engine/templates/` follows the same layout so
`template_manager.py` and the backend bundler can treat them uniformly.

## Required layout

```text
engine/templates/<template-id>/
  manifest.json    # id, display name, routing keywords, default flag, entry
  base.js          # contract + DOM bootstrap; re-exports the class
  dep/             # private engine implementation
    engine.js
    styles.css
    ...
  example/         # generated example game.js files (excluded from bundle)
```

No HTML file is stored in the template. The browser page is a bare
`<body><script type="module" src="…/base.js"></script></body>` shell
generated on demand by `engine/serve.py` (dev) or the backend bundler
(prod), using `manifest["entry"]` as the script src. Everything else
— title, stylesheet link, mount node — is created by `base.js` at
load time.

No per-template README. `base.js` is the contract: it exports a `HOOKS`
array — the machine-readable list of every overridable method a generated
`game.js` may use. The top-of-file comment points at `HOOKS`.

## `manifest.json`

```json
{
  "id": "snake",
  "name": "Snake",
  "description": "Grid-based collecting and growing game.",
  "routing_keywords": ["snake", "worm", "grid movement", "grow", "food"],
  "default": true,
  "entry": "base.js"
}
```

- `id` must match the folder name.
- `routing_keywords` are matched case-insensitively; most matches wins.
- `default: true` marks the fallback when no keyword matches. Exactly one
  template should set this.
- `entry` is the JS file loaded by the generated HTML shell (usually
  `base.js`).

## `base.js` — the contract and DOM bootstrap

- Imports the game class from `./dep/engine.js` and re-exports it.
- Exports a `mount(GameClass?)` helper that sets the document title,
  injects a `<link>` to `./dep/styles.css`, creates the mount node, and
  instantiates the class.
- Queues a deferred `mount()` via `queueMicrotask` so a direct load
  renders the default game, while a subclass entry (e.g. an example
  file) can call `mount(Subclass)` synchronously and take precedence.
- Exports `HOOKS` — the machine-readable contract listing every
  overridable method name, signature, summary, and default. This is
  the single source of truth for what a generated `game.js` may
  override. Hooks are added iteratively per `template_workflow.md`.
- Hook metadata may also declare ranges or allowed values when useful.

## `dep/` — private implementation

- `engine.js` — all game logic, rendering, and input.
- `styles.css` — all template styles. Loaded by `base.js`, not by any
  HTML file.
- Add further files here as the template grows.
- Generated `game.js` files must **not** import from `dep/` directly —
  only from `../base.js`. Files inside `dep/` may be reorganized freely
  without breaking any generated game.

## Mobile and vertical support

Every template must be playable on a phone-sized vertical screen. The
game area should scale to the viewport without horizontal scrolling,
clipped controls, or text overlap. Keep the player, primary hazards,
score, and important feedback readable in a portrait layout, with the
main action near the center so generated games are ready for mobile play
and short-form vertical clips.

## `example/`

- Holds generated example subclasses named
  `game_YYMMDD_HHMM_<slug>.js` (e.g. `game_260704_0919_rainbow.js`).
  See `template_workflow.md` for the required shape.
- Excluded from the shipped bundle. Useful for local verification of new
  customization hooks and as few-shot examples when the backend prompts
  the code agent for a user request.

## How generated games plug in

The user-specific `game.js` is **not** part of the template folder. The
backend:

1. Picks a template via `TemplateManager.select(user_requirement)`.
2. Copies `template.bundle_files` (everything except `example/`) into a
   per-request bundle directory.
3. Writes a generated `game.js` that imports the class from `./base.js`,
   extends it, and calls `mount(SubClass)`.
4. Generates a bare HTML shell whose module script points at
   `./game.js` instead of `./base.js`.
5. Serves the bundle to the frontend.

The template folder itself is immutable per request.

## Registering a new template

1. Create `engine/templates/<id>/` following the layout above.
2. Give it unique `routing_keywords`.
3. Set `default: true` on exactly one template family.

No code changes to `template_manager.py` are needed — templates are
discovered by scanning the folder.

## Tooling guardrails

- Validation should confirm that every declared hook exists on the exported
  class, and that examples override only declared hooks.
- The dev server should tolerate port reuse, parallel requests, and clients
  disconnecting before a response completes.
