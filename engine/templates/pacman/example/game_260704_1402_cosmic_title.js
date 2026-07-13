/**
 * @demonstrates: getGameTitle override for a cosmic arcade identity.
 *   Expected outcome: "Cosmic Chomp" appears in the header and
 *   browser title while gameplay remains unchanged.
 */
import { PacManGame, mount } from "../base.js";

class CosmicTitlePacMan extends PacManGame {
  getGameTitle() {
    return "Cosmic Chomp";
  }
}

mount(CosmicTitlePacMan);
