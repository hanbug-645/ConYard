/**
 * @demonstrates: Big dynamic mutant for surprise and comeback hype.
 *   The fifth snack becomes a visible jackpot: the board glows, the
 *   food turns into a gem, and getFoodScoreValue gives a five-point
 *   score spike when the player grabs it.
 */
import { SnakeGame, mount } from "../base.js";

class JackpotSnackSnake extends SnakeGame {
  getGameTitle() {
    return "Jackpot Snake";
  }

  getGameSubtitle() {
    return "When the board turns gold, grab the gem.";
  }

  getTargetScore() {
    return 12;
  }

  getFoodScoreValue(score) {
    return score === 4 ? 5 : 1;
  }

  getMoveDelay(score) {
    return score === 4 ? 68 : Math.max(56, 110 - score * 4);
  }

  getBoardBackgroundColor() {
    if (this.score === 4) return "#2a1c05";
    if (this.score > 4) return "#171124";
    return "#0d1928";
  }

  getGridColor() {
    if (this.score === 4) return "#facc15";
    if (this.score > 4) return "#a855f7";
    return "#28425e";
  }

  getSnakeCellColor(index) {
    if (this.score === 4) return index === 0 ? "#fff7ad" : "#f97316";
    return index === 0 ? "#f5f3ff" : "#8b5cf6";
  }

  getFoodColor() {
    return this.score === 4 ? "#fde047" : "#c084fc";
  }

  getFoodShape() {
    return "diamond";
  }

  getFoodEmoji() {
    return this.score === 4 ? "💎" : null;
  }

  getOverlayContent(mode) {
    const copy = super.getOverlayContent(mode);
    const jackpotCopy = {
      start: {
        title: "Jackpot run",
        message: "The fifth snack becomes a five-point gem.",
        action: "Chase jackpot"
      },
      won: {
        title: "Jackpot cashed",
        message: "The gem paid out.",
        action: "Spin again"
      },
      lost: {
        title: "Jackpot missed",
        message: "The shine was distracting.",
        action: "Try again"
      }
    };
    return jackpotCopy[mode] || copy;
  }
}

mount(JackpotSnackSnake);
