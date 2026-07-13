/**
 * @demonstrates: getTargetScore override for a short sprint.
 *   Expected outcome: clearing three pipe pairs wins the game.
 */
import { FlappyBirdGame, mount } from "../base.js";

class SprintTargetFlappy extends FlappyBirdGame {
  getTargetScore() {
    return 3;
  }
}

mount(SprintTargetFlappy);
