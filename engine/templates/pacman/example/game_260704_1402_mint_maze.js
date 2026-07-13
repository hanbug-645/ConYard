/**
 * @demonstrates: getWallPalette override for a cool mint maze.
 *   Expected outcome: maze walls use deep teal fill with bright mint
 *   outlines.
 */
import { PacManGame, mount } from "../base.js";

class MintMazePacMan extends PacManGame {
  getWallPalette() {
    return { fill: "#0f766e", edge: "#5eead4" };
  }
}

mount(MintMazePacMan);
