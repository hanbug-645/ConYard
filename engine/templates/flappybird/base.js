/**
 * Flappy Bird template contract.
 *
 * This is the ONLY file a generated game.js should import from.
 * It re-exports FlappyBirdGame from ./dep/engine.js and bootstraps the
 * DOM when loaded directly.
 *
 * HOOKS is the complete machine-readable customization contract.
 */
import { FlappyBirdGame } from "./dep/engine.js";

export { FlappyBirdGame };

export const HOOKS = [
  {
    name: "getGameTitle",
    signature: "() => string",
    summary: "Game name shown in the header and browser title.",
    default: "Flappy Bird",
  },
  {
    name: "getGameSubtitle",
    signature: "() => string",
    summary: "Short mood-setting line shown below the title.",
    default: "Thread the gaps. Keep flying.",
  },
  {
    name: "getBirdColor",
    signature: "() => string",
    summary: "CSS color used to draw the bird.",
    default: "#ffd84d",
  },
  {
    name: "getSkyPalette",
    signature: "() => { top: string, bottom: string }",
    summary: "Top and bottom colors of the sky gradient.",
    default: "{ top: \"#65c8f5\", bottom: \"#d8f3ff\" }",
  },
  {
    name: "getPipePalette",
    signature: "() => { fill: string, edge: string }",
    summary: "Fill and outline colors used for pipes.",
    default: "{ fill: \"#58be4b\", edge: \"#267b34\" }",
  },
  {
    name: "getGravity",
    signature: "() => number",
    summary: "Downward acceleration applied on each animation step.",
    default: "0.42",
  },
  {
    name: "getFlapStrength",
    signature: "() => number",
    summary: "Upward velocity applied when the player flaps.",
    default: "-7.2",
  },
  {
    name: "getPipeGap",
    signature: "() => number",
    summary: "Vertical opening between each pipe pair in pixels.",
    default: "158",
  },
  {
    name: "getPipeSpeed",
    signature: "() => number",
    summary: "Horizontal pipe movement in pixels per animation step.",
    default: "2.6",
  },
  {
    name: "getTargetScore",
    signature: "() => number",
    summary: "Number of cleared pipe pairs required to win.",
    default: "10",
  },
];

export function mount(GameClass = FlappyBirdGame) {
  if (!document.querySelector("link[data-flappy-styles]")) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = new URL("./dep/styles.css", import.meta.url).href;
    link.dataset.flappyStyles = "true";
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

