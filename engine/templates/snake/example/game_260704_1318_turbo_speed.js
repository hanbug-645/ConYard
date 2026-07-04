/**
 * @demonstrates: getMoveDelay override for a fast arcade pace that
 *   accelerates with score. Expected outcome: movement starts faster
 *   than default and becomes increasingly frantic.
 */
import { SnakeGame, mount } from "../base.js";

class TurboSnake extends SnakeGame {
  getMoveDelay(score) {
    return Math.max(45, 90 - score * 4);
  }
}

mount(TurboSnake);
