/**
 * @demonstrates: getGameSubtitle override for a spooky maze mood.
 *   Expected outcome: the header tagline warns that the maze is
 *   haunted.
 */
import { PacManGame, mount } from "../base.js";

class SpookyTaglinePacMan extends PacManGame {
  getGameSubtitle() {
    return "One hungry hero. One very haunted maze.";
  }
}

mount(SpookyTaglinePacMan);
