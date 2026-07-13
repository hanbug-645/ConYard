/**
 * @demonstrates: getPelletStyle override for large pink collectibles.
 *   Expected outcome: pellets are larger and vivid pink while scoring
 *   remains unchanged.
 */
import { PacManGame, mount } from "../base.js";

class BigPelletPacMan extends PacManGame {
  getPelletStyle() {
    return { color: "#ff69b4", radius: 4.5 };
  }
}

mount(BigPelletPacMan);
