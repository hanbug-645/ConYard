/**
 * @demonstrates: getGravity override for a floaty low-gravity mode.
 *   Expected outcome: the bird falls more slowly between flaps.
 */
import { FlappyBirdGame, mount } from "../base.js";

class MoonGravityFlappy extends FlappyBirdGame {
  getGravity() {
    return 0.2;
  }
}

mount(MoonGravityFlappy);
