/**
 * @demonstrates: getGhostChaseProbability override for gentler ghost
 *   behavior. Expected outcome: ghosts choose random routes more often
 *   and pursue the player less consistently.
 */
import { PacManGame, mount } from "../base.js";

class RelaxedGhostPacMan extends PacManGame {
  getGhostChaseProbability() {
    return 0.2;
  }
}

mount(RelaxedGhostPacMan);
