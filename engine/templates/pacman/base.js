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

export const HOOKS = [];

export function mount(GameClass = PacManGame) {
  document.title = "PacMan";

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

