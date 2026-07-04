/**
 * @demonstrates: getFoodEmoji override using a strawberry character.
 *   Expected outcome: the geometric collectible is replaced by a
 *   strawberry emoji while scoring behavior stays unchanged.
 */
import { SnakeGame, mount } from "../base.js";

class StrawberryFoodSnake extends SnakeGame {
  getFoodEmoji() {
    return "🍓";
  }
}

mount(StrawberryFoodSnake);
