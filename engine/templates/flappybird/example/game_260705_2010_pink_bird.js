/**
 * @demonstrates: getBirdColor override using vivid pink.
 *   Expected outcome: the bird body is pink instead of yellow.
 */
import { FlappyBirdGame, mount } from "../base.js";

class PinkBirdFlappy extends FlappyBirdGame {
  getBirdColor() {
    return "#ff5ca8";
  }
}

mount(PinkBirdFlappy);
