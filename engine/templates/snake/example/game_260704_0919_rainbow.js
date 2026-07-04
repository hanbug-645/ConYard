/**
 * @demonstrates: getSnakeCellColor override — head and every body
 *   segment cycle through the HSL hue wheel, producing a moving
 *   rainbow snake. Expected outcome: snake segments are visibly
 *   different colors spanning red → violet along its length.
 */
import { SnakeGame, mount } from "../base.js";

class RainbowSnake extends SnakeGame {
  getSnakeCellColor(index, total) {
    const hue = Math.round((index / Math.max(total, 1)) * 360);
    return `hsl(${hue}, 90%, 60%)`;
  }
}

mount(RainbowSnake);
