/**
 * @demonstrates: Big dynamic mutant for surprise payout. At score 90,
 *   the maze turns gold and the next pellet is worth 100 points, giving
 *   the bonus a clear visual cue before the score spike.
 */
import { PacManGame, mount } from "../base.js";

class JackpotPelletPacMan extends PacManGame {
  getGameTitle() {
    return "Jackpot Maze";
  }

  getGameSubtitle() {
    return "When the maze glows gold, one pellet pays out big.";
  }

  getPelletScoreValue(score) {
    return score === 90 ? 100 : 10;
  }

  getStepDelay() {
    return this.score === 90 ? 70 : 115;
  }

  getBoardBackgroundColor() {
    if (this.score === 90) return "#2a1c05";
    if (this.score > 90) return "#171124";
    return "#050711";
  }

  getWallPalette() {
    return this.score === 90
      ? { fill: "#854d0e", edge: "#fde047" }
      : { fill: "#312e81", edge: "#a78bfa" };
  }

  getPelletStyle() {
    return {
      color: this.score === 90 ? "#fde047" : "#f5d0fe",
      radius: this.score === 90 ? 5.4 : 2.7
    };
  }

  getPlayerColor() {
    return this.score === 90 ? "#fff7ad" : "#ffd52a";
  }
}

mount(JackpotPelletPacMan);
