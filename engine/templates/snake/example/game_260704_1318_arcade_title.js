/**
 * @demonstrates: getGameTitle override that gives the game a punchy
 *   arcade identity. Expected outcome: "Byte Bites" appears in the
 *   header and browser title while gameplay remains unchanged.
 */
import { SnakeGame, mount } from "../base.js";

class ArcadeTitleSnake extends SnakeGame {
  getGameTitle() {
    return "Byte Bites";
  }
}

mount(ArcadeTitleSnake);
