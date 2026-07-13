/**
 * @demonstrates: getGhostColors override with a candy-colored palette.
 *   Expected outcome: the two ghosts render in violet and orange.
 */
import { PacManGame, mount } from "../base.js";

class CandyGhostPacMan extends PacManGame {
  getGhostColors() {
    return ["#a855f7", "#ff8a3d"];
  }
}

mount(CandyGhostPacMan);
