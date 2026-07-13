/**
 * @demonstrates: Cosmetic identity mutant using remote enemy images.
 *   getGhostImageUrls turns both ghosts into Doge heads while the player
 *   remains the normal PacMan shape.
 *
 * Image source: https://pngimg.com/image/104491
 * License: CC BY-NC 4.0
 */
import { PacManGame, mount } from "../base.js";

class DogeGhostPacMan extends PacManGame {
  getGameSubtitle() {
    return "The maze is full of suspiciously cheerful ghosts.";
  }

  getGhostImageUrls() {
    return [
      "https://pngimg.com/uploads/doge_meme/doge_meme_PNG3.png",
      "https://pngimg.com/uploads/doge_meme/doge_meme_PNG3.png"
    ];
  }
}

mount(DogeGhostPacMan);
