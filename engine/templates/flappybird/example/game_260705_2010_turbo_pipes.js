/**
 * @demonstrates: getPipeSpeed override for a fast arcade challenge.
 *   Expected outcome: pipes move across the screen much faster.
 */
import { FlappyBirdGame, mount } from "../base.js";

class TurboPipeFlappy extends FlappyBirdGame {
  getPipeSpeed() {
    return 4.8;
  }
}

mount(TurboPipeFlappy);
