/**
 * @demonstrates: getGameSubtitle override for a calmer personality.
 *   Expected outcome: the line under the title reads like a relaxed,
 *   low-pressure invitation.
 */
import { SnakeGame, mount } from "../base.js";

class ChillTaglineSnake extends SnakeGame {
  getGameSubtitle() {
    return "Slow loops, tiny snacks, no worries.";
  }
}

mount(ChillTaglineSnake);
