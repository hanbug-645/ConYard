/**
 * PacMan template contract.
 *
 * This is the ONLY file a generated game.js should import from.
 * It re-exports PacManGame from ./dep/engine.js and bootstraps the DOM
 * when loaded directly.
 *
 * HOOKS is intentionally empty for the initial template. Customization
 * interfaces are added one at a time through engine/template_workflow.md.
 */
import { PacManGame } from "./dep/engine.js";

export { PacManGame };

export const HOOKS = [
  {
    name: "getGameTitle",
    signature: "() => string",
    summary: "Game name shown in the header and browser title.",
    default: "PacMan",
  },
  {
    name: "getGameSubtitle",
    signature: "() => string",
    summary: "Short mood-setting line shown below the game title.",
    default: "Clear the maze. Outsmart the ghosts.",
  },
  {
    name: "getPlayerColor",
    signature: "() => string",
    summary: "CSS color used to draw the player.",
    default: "#ffd52a",
  },
  {
    name: "getPlayerImageUrl",
    signature: "() => string | null",
    summary: "Image URL used to draw the player, or null to use the default PacMan shape.",
    default: "null",
  },
  {
    name: "getGhostColors",
    signature: "() => string[]",
    summary: "CSS color palette assigned to ghosts in order.",
    default: "[\"#ff4d6d\", \"#42dff5\"]",
  },
  {
    name: "getGhostImageUrls",
    signature: "() => string[]",
    summary: "Image URLs assigned to ghosts in order. Missing entries use colored ghost shapes.",
    default: "[]",
  },
  {
    name: "getBoardBackgroundColor",
    signature: "() => string",
    summary: "CSS color painted behind the maze.",
    default: "#050711",
  },
  {
    name: "getWallPalette",
    signature: "() => { fill: string, edge: string }",
    summary: "Fill and outline colors used for maze walls.",
    default: "{ fill: \"#3155ff\", edge: \"#7d91ff\" }",
  },
  {
    name: "getPelletStyle",
    signature: "() => { color: string, radius: number }",
    summary: "CSS color and pixel radius used for maze pellets.",
    default: "{ color: \"#ffe6b3\", radius: 2.5 }",
  },
  {
    name: "getStepDelay",
    signature: "() => number",
    summary: "Milliseconds between game movement ticks.",
    default: "135",
  },
  {
    name: "getControlMode",
    signature: "(score: number, lives: number) => \"normal\" | \"inverted\"",
    summary: "Direction mapping for player input at the current score and lives.",
    default: "normal",
  },
  {
    name: "getPelletScoreValue",
    signature: "(score: number) => number",
    summary: "How many points the next pellet is worth.",
    default: "10",
  },
  {
    name: "getHazardCells",
    signature: "(score: number) => Array<{ x: number, y: number }>",
    summary: "Maze cells that act as extra hazards and cost a life on contact.",
    default: "[]",
  },
  {
    name: "getHazardColor",
    signature: "(score: number) => string",
    summary: "CSS color used when drawing hazard cells.",
    default: "#ff3d71",
  },
  {
    name: "getStartingLives",
    signature: "() => number",
    summary: "Number of lives available at the start of a game.",
    default: "3",
  },
  {
    name: "getGhostChaseProbability",
    signature: "() => number",
    summary: "Chance from 0 to 1 that a ghost chooses its shortest path.",
    default: "0.72",
  },
  {
    name: "getOverlayContent",
    signature: "(mode: string, context: object) => { title: string, message: string, action: string }",
    summary: "Copy shown for start, pause, caught, won, and lost overlays.",
    default: "Standard maze-chase status messages.",
  },
];

export function mount(GameClass = PacManGame) {
  if (!document.querySelector("link[data-pacman-styles]")) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = new URL("./dep/styles.css", import.meta.url).href;
    link.dataset.pacmanStyles = "true";
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

queueMicrotask(() => {
  if (!document.querySelector("#game-root")) mount();
});
