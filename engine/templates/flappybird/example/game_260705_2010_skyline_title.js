/**
 * @demonstrates: getGameTitle override for a city-flight identity.
 *   Expected outcome: "Skyline Hopper" appears in the header and
 *   browser title.
 */
import { FlappyBirdGame, mount } from "../base.js";

class SkylineTitleFlappy extends FlappyBirdGame {
  getGameTitle() {
    return "Skyline Hopper";
  }
}

mount(SkylineTitleFlappy);
