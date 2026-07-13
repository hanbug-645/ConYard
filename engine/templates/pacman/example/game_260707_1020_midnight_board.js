/**
 * @demonstrates: Cosmetic identity mutant for board atmosphere.
 *   getBoardBackgroundColor gives the maze a midnight arcade floor
 *   while the core chase rules stay unchanged.
 */
import { PacManGame, mount } from "../base.js";

class MidnightBoardPacMan extends PacManGame {
  getBoardBackgroundColor() {
    return "#130f24";
  }

  getWallPalette() {
    return { fill: "#312e81", edge: "#a78bfa" };
  }
}

mount(MidnightBoardPacMan);
