/**
 * @demonstrates: getGridColor override for a bright synthwave grid.
 *   Expected outcome: vivid pink grid lines appear across the default
 *   dark board.
 */
import { SnakeGame, mount } from "../base.js";

class NeonGridSnake extends SnakeGame {
  getGridColor() {
    return "#ff4fd8";
  }
}

mount(NeonGridSnake);
