/**
 * @demonstrates: getPipeGap override for a forgiving beginner mode.
 *   Expected outcome: pipe openings are substantially taller.
 */
import { FlappyBirdGame, mount } from "../base.js";

class EasyGapFlappy extends FlappyBirdGame {
  getPipeGap() {
    return 230;
  }
}

mount(EasyGapFlappy);
