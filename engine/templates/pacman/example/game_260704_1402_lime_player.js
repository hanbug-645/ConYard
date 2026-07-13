/**
 * @demonstrates: getPlayerColor override using electric lime.
 *   Expected outcome: the player is lime green instead of yellow.
 */
import { PacManGame, mount } from "../base.js";

class LimePlayerPacMan extends PacManGame {
  getPlayerColor() {
    return "#b7ff38";
  }
}

mount(LimePlayerPacMan);
