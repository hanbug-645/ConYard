/**
 * @demonstrates: getBoardBackgroundColor override for a deep plum
 *   playfield. Expected outcome: the area behind the grid changes
 *   color without affecting the surrounding page.
 */
import { SnakeGame, mount } from "../base.js";

class PlumBoardSnake extends SnakeGame {
  getBoardBackgroundColor() {
    return "#24103f";
  }
}

mount(PlumBoardSnake);
