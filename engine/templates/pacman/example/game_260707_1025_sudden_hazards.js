/**
 * @demonstrates: Big dynamic mutant for sudden obstacle pressure.
 *   getHazardCells adds danger tiles after score 60, with warning
 *   colors and sharper pellets to make panic mode obvious.
 */
import { PacManGame, mount } from "../base.js";

class SuddenHazardsPacMan extends PacManGame {
  getHazardCells(score) {
    if (score < 60) return [];
    const hazards = [
      { x: 6, y: 2 },
      { x: 14, y: 2 },
      { x: 2, y: 10 },
      { x: 18, y: 10 }
    ];
    if (score >= 140) {
      hazards.push({ x: 6, y: 14 }, { x: 14, y: 14 });
    }
    return hazards;
  }

  getHazardColor(score) {
    return score >= 140 ? "#ff2d75" : "#ff8a3d";
  }

  getBoardBackgroundColor() {
    return this.score >= 60 ? "#201124" : "#06111f";
  }

  getWallPalette() {
    return this.score >= 60
      ? { fill: "#701a75", edge: "#f0abfc" }
      : { fill: "#0f3b76", edge: "#67e8f9" };
  }

  getPelletStyle() {
    return {
      color: this.score >= 60 ? "#fef08a" : "#d9f99d",
      radius: this.score >= 60 ? 3.6 : 2.5
    };
  }
}

mount(SuddenHazardsPacMan);
