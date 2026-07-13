/**
 * @demonstrates: getPipePalette override for candy-colored obstacles.
 *   Expected outcome: pipes use purple fill and bright pink outlines.
 */
import { FlappyBirdGame, mount } from "../base.js";

class CandyPipeFlappy extends FlappyBirdGame {
  getPipePalette() {
    return { fill: "#8b5cf6", edge: "#ff7ac8" };
  }
}

mount(CandyPipeFlappy);
