# Template Iteration Workflow

This document describes how to grow a template over time. The folder
layout itself is fixed — see `template.md`. What changes here is the
**customization interface** exposed by `base.js` (backed by code in
`dep/`) and the collection of verified example games under `example/`.

## Philosophy

Start with the smallest possible template: `dep/` contains a hardcoded,
runnable game and `base.js` re-exports the class with **no** override
hooks. Then add one customization interface at a time, driven by what
user requests actually ask for.

Every iteration keeps two invariants:

1. The bootstrap HTML shell + `base.js` + `dep/` alone still renders
   a playable default game (`/run/base.js` works unchanged).
2. A generated `game.js` can override the new interface by extending the
   class re-exported from `base.js` — nothing else.

## Starting state

A new template begins with:

- `dep/engine.js` holding all game logic with hardcoded constants.
- `base.js` re-exporting the class, exporting `mount`, and exporting an
  empty `HOOKS` array.
- No overridable methods exposed yet.
- `example/` empty.

`templates/snake/` has already gone through one iteration
(`getSnakeCellColor`). Its current `HOOKS` and `example/` reflect that.

## Adding a customization interface

Do one focused change at a time.

### 1. Pick one thing users want to customize

Rough priority:

- Background color
- Snake body / head color
- Food color or shape
- Board dimensions
- Movement speed
- Target score
- Wall behavior (solid vs wrap)
- Obstacles
- Snake sprite / image
- Sound effects
- Title and subtitle text

Pick one. Do not batch.

### 2. Extract the value into an override point

Two supported patterns.

**Config pattern** — for plain values. In `dep/engine.js`:

```js
export class SnakeGame {
  getConfig() {
    return { boardBackground: "#0d1928" };
  }
  // ...use this.config.boardBackground instead of the hardcoded constant
}
```

Subclasses override `getConfig()`; `super.getConfig()` supplies defaults.

**Hook pattern** — for behavior:

```js
onScore(score) {}      // called after each food eaten
onEnd(result) {}       // called on win or lose
drawFood(ctx, cell) { /* default rendering */ }
```

Subclasses override the specific hook without touching the game loop.

### 3. Update the `HOOKS` export in `base.js`

Add an entry to the `HOOKS` array in `base.js`:

```js
{
  name: "getSnakeCellColor",
  signature: "(index: number, total: number) => string",
  summary: "CSS color for a snake segment. index=0 is the head.",
  default: "Head color for the head, body color otherwise.",
}
```

`HOOKS` is the machine-readable contract — the smoke test checks that
every hook overridden by an example is listed here, and the backend
uses it when prompting the code agent. If it isn't in `HOOKS`,
generated code should not rely on it.

### 4. Keep the default working

Run `python3 -m engine.serve snake` and open `http://localhost:8765/run/base.js`.
The default game must render identically to before. If behavior
changed, the extraction is wrong.

### 5. Generate a verification example

Write a new file under `example/` named:

```
game_YYMMDD_HHMM_<slug>.js
```

for example `game_260704_0919_rainbow.js`. The slug is a short,
lower-case hint at what the example demonstrates.

Required shape:

```js
/**
 * @demonstrates: <one to three sentences describing the customization
 *   and the expected visual outcome. This tag is shown on the index
 *   page and used by the backend to pick few-shot examples.>
 */
import { SnakeGame, mount } from "../base.js";

class Example extends SnakeGame {
  // override only the new hook added in this iteration
}

mount(Example);
```

The example must:

- import only from `../base.js` (never from `dep/`),
- override only methods listed in `HOOKS`,
- end with a `mount(...)` call.

### 6. Run the example to verify

Start the dev server once:

```
python3 -m engine.serve snake
```

Open `http://localhost:8765/`. You get an auto-generated index of
`base.js` and every file in `example/`, each with its `@demonstrates`
blurb. Click one to load it. No server restart needed when adding new
examples — refresh the index.

### 7. Run the smoke test

```
python3 -m engine.check_examples snake
```

Static checks: filename convention, `@demonstrates` tag, import
discipline, `mount()` call, and every overridden hook is declared in
`HOOKS`. Run this after adding or changing any example, and any time
you change `HOOKS` in `base.js`.

### 8. Keep verified examples

Do not delete old files under `example/`. They serve two purposes:

- Regression sanity checks after future interface changes.
- Few-shot examples the backend feeds the code agent when generating a
  new user `game.js`. More examples of what customizations look like
  make the generator more reliable.

## When not to add a hook

- The customization has never been requested.
- It would expose internal state (snake array, timer id, canvas
  context).
- It would allow subclasses to break the game loop, input handling, or
  collision rules.

Keep the core loop private inside `dep/`. Only expose values and
well-scoped behavior extension points through `base.js`.

## Adding a new template family

Follow the same starting-state rule: one runnable file in `dep/`, thin
`base.js` with no interfaces, empty `example/`. Grow it the same way.
The folder layout is defined in `template.md`.
