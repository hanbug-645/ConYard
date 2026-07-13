/**
 * @demonstrates: Big dynamic mutant for control panic. At score 80,
 *   getControlMode reverses inputs and the maze shifts into a warning
 *   palette so the rule change is visible immediately.
 */
import { PacManGame, mount } from "../base.js";

class SuddenReversePacMan extends PacManGame {
  getControlMode(score) {
    return score >= 80 ? "inverted" : "normal";
  }

  getBoardBackgroundColor() {
    return this.score >= 80 ? "#2b0714" : "#070b1a";
  }

  getWallPalette() {
    return this.score >= 80
      ? { fill: "#7f1d1d", edge: "#fb7185" }
      : { fill: "#1d4ed8", edge: "#93c5fd" };
  }

  getPlayerColor() {
    return this.score >= 80 ? "#fff7ad" : "#ffd52a";
  }

  getPelletStyle() {
    return {
      color: this.score >= 80 ? "#fb7185" : "#ffe6b3",
      radius: this.score >= 80 ? 3.8 : 2.5
    };
  }

  getOverlayContent(mode, context) {
    const copy = super.getOverlayContent(mode, context);
    if (mode === "start") {
      return {
        title: "Sudden Reverse",
        message: "Reach 80 points and every turn flips.",
        action: "Enter maze"
      };
    }
    return copy;
  }
}

mount(SuddenReversePacMan);
