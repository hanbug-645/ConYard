/**
 * @demonstrates: getOverlayContent override for a space-adventure
 *   narrative. Expected outcome: every overlay uses mission-themed
 *   titles, messages, and actions.
 */
import { PacManGame, mount } from "../base.js";

class SpaceOverlayPacMan extends PacManGame {
  getOverlayContent(mode, context) {
    const defaults = super.getOverlayContent(mode, context);
    const copy = {
      start: {
        title: "Launch ready",
        message: "Collect every star before the aliens close in.",
        action: "Launch mission"
      },
      pause: {
        title: "Orbit holding",
        message: "The mission is safely suspended.",
        action: "Resume flight"
      },
      caught: {
        title: "Ship hit",
        message: `${context.lives} reserve ships remaining.`,
        action: "Re-enter maze"
      },
      won: {
        title: "Sector cleared",
        message: `Mission score: ${context.score}`,
        action: "Fly again"
      },
      lost: {
        title: "Mission ended",
        message: "The alien patrol won this round.",
        action: "Relaunch"
      }
    };
    return copy[mode] || defaults;
  }
}

mount(SpaceOverlayPacMan);
