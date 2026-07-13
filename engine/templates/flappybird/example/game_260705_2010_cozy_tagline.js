/**
 * @demonstrates: getGameSubtitle override for a cozy personality.
 *   Expected outcome: the tagline describes a gentle cloud-hopping
 *   journey.
 */
import { FlappyBirdGame, mount } from "../base.js";

class CozyTaglineFlappy extends FlappyBirdGame {
  getGameSubtitle() {
    return "A tiny flight through soft morning clouds.";
  }
}

mount(CozyTaglineFlappy);
