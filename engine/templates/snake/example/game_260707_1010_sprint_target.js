/**
 * @demonstrates: Minor mechanic mutant for sprint tension. A compact
 *   board, short target, faster movement, lightning food, and urgent
 *   colors make this feel like a clear speed-run mode.
 */
import { SnakeGame, mount } from "../base.js";

class SprintTargetSnake extends SnakeGame {
  getGameTitle() {
    return "Snake Sprint";
  }

  getGameSubtitle() {
    return "Seven snacks. Small arena. No warm-up.";
  }

  getBoardDimensions() {
    return { columns: 12, rows: 10 };
  }

  getTargetScore() {
    return 7;
  }

  getMoveDelay(score) {
    return Math.max(42, 78 - score * 5);
  }

  getBoardBackgroundColor() {
    return "#12111f";
  }

  getGridColor() {
    return "#f97316";
  }

  getSnakeCellColor(index) {
    return index === 0 ? "#fff7ad" : "#22d3ee";
  }

  getFoodEmoji() {
    return "⚡";
  }

  getOverlayContent(mode) {
    const copy = super.getOverlayContent(mode);
    const sprintCopy = {
      start: {
        title: "Sprint mode",
        message: "Hit 7 snacks before the board starts feeling tiny.",
        action: "Launch sprint"
      },
      won: {
        title: "Sprint cleared",
        message: "Fast hands, clean line.",
        action: "Run it back"
      },
      lost: {
        title: "Sprint wiped",
        message: "Short boards punish wide turns.",
        action: "Retry sprint"
      }
    };
    return sprintCopy[mode] || copy;
  }
}

mount(SprintTargetSnake);
