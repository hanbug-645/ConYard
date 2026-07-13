/**
 * @demonstrates: Cosmetic identity mutant using a remote character
 *   image URL. getPlayerImageUrl renders the player as the Doge meme
 *   while maze movement and scoring stay unchanged.
 *
 * Image source: https://pngimg.com/image/104491
 * License: CC BY-NC 4.0
 */
import { PacManGame, mount } from "../base.js";

class DogePlayerPacMan extends PacManGame {
  getGameTitle() {
    return "Doge Chomp";
  }

  getPlayerImageUrl() {
    return "https://pngimg.com/uploads/doge_meme/doge_meme_PNG3.png";
  }
}

mount(DogePlayerPacMan);
