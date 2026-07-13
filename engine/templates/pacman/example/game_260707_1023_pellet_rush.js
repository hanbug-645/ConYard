/**
 * @demonstrates: Minor mechanic mutant for rush-mode clarity. Faster
 *   ticks, brighter pellets, high-value scoring, and urgent copy make
 *   the mode feel distinct instead of just numerically faster.
 */
import { PacManGame, mount } from "../base.js";

class PelletRushPacMan extends PacManGame {
  getGameTitle() {
    return "Pellet Rush";
  }

  getGameSubtitle() {
    return "Every pellet pops bigger. Keep moving.";
  }

  getStepDelay() {
    return 78;
  }

  getPelletScoreValue() {
    return 25;
  }

  getPelletStyle() {
    return { color: "#fef08a", radius: 4.2 };
  }

  getBoardBackgroundColor() {
    return "#111827";
  }

  getWallPalette() {
    return { fill: "#0f766e", edge: "#5eead4" };
  }
}

mount(PelletRushPacMan);
