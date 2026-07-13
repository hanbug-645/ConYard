/**
 * @demonstrates: getStepDelay override for a fast arcade challenge.
 *   Expected outcome: players and ghosts move substantially faster
 *   than the default game.
 */
import { PacManGame, mount } from "../base.js";

class TurboPacMan extends PacManGame {
  getStepDelay() {
    return 75;
  }
}

mount(TurboPacMan);
