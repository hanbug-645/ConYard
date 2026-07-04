/**
 * @demonstrates: getFoodShape override using the built-in diamond.
 *   Expected outcome: each collectible appears as a diamond instead
 *   of the default circle.
 */
import { SnakeGame, mount } from "../base.js";

class DiamondFoodSnake extends SnakeGame {
  getFoodShape() {
    return "diamond";
  }
}

mount(DiamondFoodSnake);
