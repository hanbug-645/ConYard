/**
 * @demonstrates: getSnakeCellImage override using the original remote
 *   Doge PNG URL for every snake segment. Expected outcome: each snake
 *   cell displays a square-cropped Doge head instead of a color block.
 *
 * Image source: https://pngimg.com/image/104491
 * License: CC BY-NC 4.0
 */
import { SnakeGame, mount } from "../base.js";

class DogeCellSnake extends SnakeGame {
  getSnakeCellImage(_index, _total) {
    return "https://pngimg.com/uploads/doge_meme/doge_meme_PNG3.png";
  }
}

mount(DogeCellSnake);
