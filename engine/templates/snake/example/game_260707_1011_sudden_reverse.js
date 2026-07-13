/**
 * @demonstrates: Big dynamic mutant for sudden reversal panic. At
 *   score 3, getControlMode flips movement and the board shifts into a
 *   hot warning palette so the panic mode is visible immediately.
 */
import { SnakeGame, mount } from "../base.js";

class SuddenReverseSnake extends SnakeGame {
  getControlMode(score) {
    return score >= 3 ? "inverted" : "normal";
  }

  getBoardBackgroundColor() {
    return this.score >= 3 ? "#2b0714" : "#101733";
  }

  getGridColor() {
    return this.score >= 3 ? "#ff4f7b" : "#304068";
  }

  getSnakeCellColor(index, total) {
    if (this.score < 3) {
      return index === 0 ? "#dbeafe" : "#74d9ff";
    }
    const heat = Math.round((index / Math.max(total, 1)) * 34);
    return index === 0 ? "#fff3a3" : `hsl(${heat}, 96%, 58%)`;
  }

  getFoodColor() {
    return this.score >= 3 ? "#ffef5a" : "#8be9fd";
  }

  getOverlayContent(mode) {
    const copy = super.getOverlayContent(mode);
    if (mode === "start") {
      return {
        title: "Sudden Reverse",
        message: "Reach 3 snacks and the controls flip.",
        action: "Start run"
      };
    }
    return copy;
  }
}

mount(SuddenReverseSnake);
