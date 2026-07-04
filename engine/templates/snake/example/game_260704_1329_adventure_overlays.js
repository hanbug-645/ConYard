/**
 * @demonstrates: getOverlayContent override for branded game-state
 *   copy. Expected outcome: start, pause, win, and loss overlays use
 *   playful Snake Adventure language.
 */
import { SnakeGame, mount } from "../base.js";

class AdventureOverlaySnake extends SnakeGame {
  getOverlayContent(mode) {
    const defaults = super.getOverlayContent(mode);
    const copy = {
      start: {
        title: "The trail begins",
        message: "Gather every relic and guard your tail.",
        action: "Begin adventure"
      },
      pause: {
        title: "Campfire break",
        message: "Your winding quest is safely paused.",
        action: "Continue quest"
      },
      won: {
        title: "Legend complete",
        message: "Every relic is yours.",
        action: "Adventure again"
      },
      lost: {
        title: "Trail interrupted",
        message: "A fresh path is waiting.",
        action: "Try a new path"
      }
    };
    return copy[mode] || defaults;
  }
}

mount(AdventureOverlaySnake);
