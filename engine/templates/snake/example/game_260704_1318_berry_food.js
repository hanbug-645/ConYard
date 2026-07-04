/**
 * @demonstrates: getFoodColor override for a berry-red collectible.
 *   Expected outcome: the default circular food is rendered in a
 *   vivid red-pink color.
 */
import { SnakeGame, mount } from "../base.js";

class BerryFoodSnake extends SnakeGame {
  getFoodColor() {
    return "#ff335f";
  }
}

mount(BerryFoodSnake);
