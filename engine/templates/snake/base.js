/**
 * Snake template contract.
 *
 * This is the ONLY file a generated game.js should import from.
 * It re-exports the SnakeGame class defined in ./dep/engine.js and,
 * when loaded directly as the page entry, bootstraps the entire DOM
 * (title, stylesheet, mount node) and instantiates the default game.
 *
 * The browser needs only a bare HTML shell with <body> and a
 * <script type="module" src="./base.js"> tag. Everything else is
 * built here.
 *
 * The `HOOKS` export below is the machine-readable contract: every
 * overridable method the code agent may implement in a generated
 * subclass. Keep it in sync with the actual methods on SnakeGame in
 * ./dep/engine.js — the smoke test in engine/check_examples.py verifies
 * that every hook named here is defined on the base class.
 *
 * See engine/template_workflow.md for how new hooks are added.
 *
 * A generated game.js extends SnakeGame, overrides the hooks it needs,
 * and instantiates the subclass against the mount node. See ./example/
 * for generated example subclasses.
 */
import { SnakeGame } from "./dep/engine.js";

export { SnakeGame };

export const HOOKS = [
  {
    name: "getGameTitle",
    signature: "() => string",
    summary: "Game name shown in the header and browser title.",
    default: "Snake",
  },
  {
    name: "getGameSubtitle",
    signature: "() => string",
    summary: "Short mood-setting line shown below the game title.",
    default: "Collect the food and keep moving.",
  },
  {
    name: "getMoveDelay",
    signature: "(score: number) => number",
    summary: "Milliseconds between movement ticks at the current score.",
    default: "120ms, decreasing by 3ms per point to a 60ms minimum.",
  },
  {
    name: "getTargetScore",
    signature: "() => number",
    summary: "Score required to win the game.",
    default: "10",
  },
  {
    name: "getBoardBackgroundColor",
    signature: "() => string",
    summary: "CSS color painted behind the game grid.",
    default: "#0d1928",
  },
  {
    name: "getGridColor",
    signature: "() => string",
    summary: "CSS color used for board grid lines.",
    default: "#17283a",
  },
  {
    name: "getFoodColor",
    signature: "() => string",
    summary: "CSS color used when drawing the collectible.",
    default: "#ffcf5a",
  },
  {
    name: "getFoodShape",
    signature: "() => \"circle\" | \"square\" | \"diamond\"",
    summary: "Built-in geometric shape used for the collectible.",
    default: "circle",
  },
  {
    name: "getFoodEmoji",
    signature: "() => string | null",
    summary: "Emoji drawn as the collectible, or null to use its shape.",
    default: "null; the collectible uses getFoodShape and getFoodColor.",
  },
  {
    name: "getWallMode",
    signature: "() => \"solid\" | \"wrap\"",
    summary: "Whether board edges cause a loss or wrap to the other side.",
    default: "solid",
  },
  {
    name: "getControlMode",
    signature: "(score: number) => \"normal\" | \"inverted\"",
    summary: "Direction mapping for player input at the current score.",
    default: "normal",
  },
  {
    name: "getFoodScoreValue",
    signature: "(score: number) => number",
    summary: "How many points the next collectible is worth.",
    default: "1",
  },
  {
    name: "getObstacleCells",
    signature: "(score: number, board: { columns: number, rows: number }) => Array<{ x: number, y: number }>",
    summary: "Board cells that behave as environmental hazards.",
    default: "[]",
  },
  {
    name: "getObstacleColor",
    signature: "(score: number) => string",
    summary: "CSS color used when drawing obstacle cells.",
    default: "#ef476f",
  },
  {
    name: "getBoardDimensions",
    signature: "() => { columns: number, rows: number }",
    summary: "Number of horizontal and vertical cells on the board.",
    default: "{ columns: 20, rows: 16 }",
  },
  {
    name: "getOverlayContent",
    signature: "(mode: \"start\" | \"pause\" | \"won\" | \"lost\") => { title: string, message: string, action: string }",
    summary: "Copy shown in the game-state overlay for the requested mode.",
    default: "Standard Ready, Paused, You win, and Game over messages.",
  },
  {
    name: "getSnakeCellColor",
    signature: "(index: number, total: number) => string",
    summary: "CSS color for a snake segment. index=0 is the head.",
    default: "Head color for the head, body color for every other segment.",
  },
  {
    name: "getSnakeCellImage",
    signature: "(index: number, total: number) => string | null",
    summary: "Image URL for a snake segment. Return null to use its color.",
    default: "null; every segment uses getSnakeCellColor.",
  },
];

export function mount(GameClass = SnakeGame) {
  if (!document.querySelector('link[data-snake-styles]')) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = new URL("./dep/styles.css", import.meta.url).href;
    link.dataset.snakeStyles = "true";
    document.head.appendChild(link);
  }

  let root = document.querySelector("#game-root");
  if (!root) {
    root = document.createElement("div");
    root.id = "game-root";
    document.body.appendChild(root);
  }
  return new GameClass(root);
}

// Auto-mount the default game if nothing else has mounted first.
// Deferred to a microtask so a subclass entry (e.g. example/game_*.js)
// can call `mount(Subclass)` synchronously and win.
queueMicrotask(() => {
  if (!document.querySelector("#game-root")) mount();
});
