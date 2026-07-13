/**
 * @demonstrates: getFlapStrength override for powerful upward boosts.
 *   Expected outcome: each flap launches the bird higher than default.
 */
import { FlappyBirdGame, mount } from "../base.js";

class RocketFlapFlappy extends FlappyBirdGame {
  getFlapStrength() {
    return -10.5;
  }
}

mount(RocketFlapFlappy);
