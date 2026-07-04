/**
 * @demonstrates: getWallMode override enabling edge wrapping.
 *   Expected outcome: leaving one side of the board moves the snake
 *   to the opposite side instead of ending the game.
 */
import { SnakeGame, mount } from "../base.js";

class WrapWallSnake extends SnakeGame {
  getWallMode() {
    return "wrap";
  }
}

mount(WrapWallSnake);
