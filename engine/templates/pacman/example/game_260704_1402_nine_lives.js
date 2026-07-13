/**
 * @demonstrates: getStartingLives override for an easier mode.
 *   Expected outcome: the game begins with nine lives.
 */
import { PacManGame, mount } from "../base.js";

class NineLivesPacMan extends PacManGame {
  getStartingLives() {
    return 9;
  }
}

mount(NineLivesPacMan);
