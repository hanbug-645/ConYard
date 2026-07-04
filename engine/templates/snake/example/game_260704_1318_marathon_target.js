/**
 * @demonstrates: getTargetScore override for a longer challenge.
 *   Expected outcome: the scoreboard target is 25 and victory occurs
 *   only after reaching that score.
 */
import { SnakeGame, mount } from "../base.js";

class MarathonSnake extends SnakeGame {
  getTargetScore() {
    return 25;
  }
}

mount(MarathonSnake);
