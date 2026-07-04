/**
 * @demonstrates: getBoardDimensions override for a compact hard-mode
 *   arena. Expected outcome: the playable grid is 10 columns by 10
 *   rows while movement, food placement, and collision remain valid.
 */
import { SnakeGame, mount } from "../base.js";

class TinyBoardSnake extends SnakeGame {
  getBoardDimensions() {
    return { columns: 10, rows: 10 };
  }
}

mount(TinyBoardSnake);
