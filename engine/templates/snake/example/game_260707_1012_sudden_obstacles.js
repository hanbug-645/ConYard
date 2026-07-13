/**
 * @demonstrates: Big dynamic mutant for sudden obstacle pressure.
 *   getObstacleCells adds hazards as score rises, and the board shifts
 *   into a warning palette when obstacles enter the arena.
 */
import { SnakeGame, mount } from "../base.js";

class SuddenObstacleSnake extends SnakeGame {
  getObstacleCells(score, board) {
    if (score < 2) return [];

    const middleY = Math.floor(board.rows / 2);
    const middleX = Math.floor(board.columns / 2);
    const hazards = [];

    for (let x = 4; x < board.columns - 4; x += 4) {
      hazards.push({ x, y: middleY });
    }
    if (score >= 5) {
      for (let y = 3; y < board.rows - 3; y += 3) {
        hazards.push({ x: middleX, y });
      }
    }

    return hazards;
  }

  getBoardBackgroundColor() {
    return this.score >= 2 ? "#210f24" : "#101828";
  }

  getGridColor() {
    return this.score >= 5 ? "#ff4f9a" : this.score >= 2 ? "#7c3aed" : "#24364d";
  }

  getSnakeCellColor(index, _total) {
    if (this.score < 2) {
      return index === 0 ? "#e0fff5" : "#5eead4";
    }
    return index === 0 ? "#fff7ad" : "#ff9f1c";
  }

  getFoodColor() {
    return this.score >= 2 ? "#fef08a" : "#a7f3d0";
  }

  getObstacleColor(score) {
    return score >= 5 ? "#ff2d75" : "#ff8a3d";
  }
}

mount(SuddenObstacleSnake);
