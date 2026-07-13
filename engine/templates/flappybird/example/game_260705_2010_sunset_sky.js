/**
 * @demonstrates: getSkyPalette override for a warm sunset flight.
 *   Expected outcome: the sky fades from coral to pale gold.
 */
import { FlappyBirdGame, mount } from "../base.js";

class SunsetSkyFlappy extends FlappyBirdGame {
  getSkyPalette() {
    return { top: "#f26b6b", bottom: "#ffd786" };
  }
}

mount(SunsetSkyFlappy);
