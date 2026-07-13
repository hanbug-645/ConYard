/**
 * Flappy Bird engine - private implementation.
 *
 * Generated game files import only from ../base.js. Physics, collision,
 * rendering, and lifecycle helpers remain private.
 */

const WIDTH = 420;
const HEIGHT = 640;
const FLOOR_HEIGHT = 72;
const BIRD_X = 112;
const BIRD_RADIUS = 15;
const PIPE_WIDTH = 66;
const PIPE_SPACING = 220;

const DEFAULTS = {
  gravity: 0.42,
  flapStrength: -7.2,
  pipeGap: 158,
  pipeSpeed: 2.6,
  targetScore: 10
};

const COLORS = {
  bird: "#ffd84d",
  birdWing: "#f5a623",
  birdEye: "#172033",
  skyTop: "#65c8f5",
  skyBottom: "#d8f3ff",
  pipeFill: "#58be4b",
  pipeEdge: "#267b34",
  ground: "#d8bf69",
  grass: "#75c84b"
};

export class FlappyBirdGame {
  constructor(root) {
    if (!(root instanceof HTMLElement)) {
      throw new TypeError("FlappyBirdGame requires a root HTMLElement.");
    }

    this.root = root;
    this.settings = this.#readSettings();
    this.bird = { y: HEIGHT * 0.46, velocity: 0, rotation: 0 };
    this.pipes = [];
    this.score = 0;
    this.state = "ready";
    this.animationId = null;
    this.lastTime = 0;
    this.spawnDistance = 0;
    this.wingFrame = 0;

    this.#renderShell();
    this.#resetGame();
  }

  #renderShell() {
    const title = this.getGameTitle();
    const subtitle = this.getGameSubtitle();
    document.title = title;

    this.root.innerHTML = `
      <main class="game-shell">
        <header class="game-header">
          <div>
            <h1>${this.#escapeText(title)}</h1>
            <p>${this.#escapeText(subtitle)}</p>
          </div>
          <div class="stats" aria-label="Game status">
            <div><span>Score</span><strong data-score>0</strong></div>
            <div><span>Target</span><strong>${this.settings.targetScore}</strong></div>
          </div>
        </header>
        <section class="board-wrap" aria-label="Flappy Bird game board">
          <canvas data-canvas></canvas>
          <div class="overlay" data-overlay>
            <div>
              <h2 data-overlay-title></h2>
              <p data-overlay-message></p>
              <button data-action type="button">Start flying</button>
            </div>
          </div>
        </section>
        <footer>
          <p>Space, ↑, W, click, or tap to flap<br>R to restart</p>
          <button class="flap-button" data-flap type="button">Flap</button>
        </footer>
      </main>
    `;

    this.canvas = this.root.querySelector("[data-canvas]");
    this.context = this.canvas.getContext("2d");
    this.scoreElement = this.root.querySelector("[data-score]");
    this.overlay = this.root.querySelector("[data-overlay]");
    this.overlayTitle = this.root.querySelector("[data-overlay-title]");
    this.overlayMessage = this.root.querySelector("[data-overlay-message]");
    this.actionButton = this.root.querySelector("[data-action]");
    this.flapButton = this.root.querySelector("[data-flap]");

    document.documentElement.style.setProperty("--board-ratio", `${WIDTH} / ${HEIGHT}`);
    this.#bindEvents();
    this.#resizeCanvas();
  }

  #bindEvents() {
    this.actionButton.addEventListener("click", () => this.#flap());
    this.flapButton.addEventListener("pointerdown", () => this.#flap());
    this.canvas.addEventListener("pointerdown", () => this.#flap());

    document.addEventListener("keydown", (event) => {
      if (
        event.code === "Space" ||
        event.key === "ArrowUp" ||
        event.key === "w" ||
        event.key === "W"
      ) {
        event.preventDefault();
        this.#flap();
      } else if (event.key === "r" || event.key === "R") {
        this.#resetGame();
        this.#start();
      }
    });

    window.addEventListener("resize", () => this.#resizeCanvas());
    document.addEventListener("visibilitychange", () => {
      if (document.hidden && this.state === "playing") this.#pause();
    });
  }

  #resetGame() {
    this.#stopAnimation();
    this.bird = { y: HEIGHT * 0.46, velocity: 0, rotation: 0 };
    this.pipes = [];
    this.score = 0;
    this.spawnDistance = PIPE_SPACING * 0.55;
    this.scoreElement.textContent = "0";
    this.state = "ready";
    this.#showOverlay(
      "Ready to fly?",
      "Flap through the pipe gaps without touching anything.",
      "Start flying"
    );
    this.#draw();
  }

  #start() {
    if (this.state === "won" || this.state === "lost") this.#resetGame();
    this.state = "playing";
    this.overlay.hidden = true;
    this.lastTime = performance.now();
    this.animationId = requestAnimationFrame((time) => this.#frame(time));
  }

  #pause() {
    this.#stopAnimation();
    this.state = "ready";
    this.#showOverlay("Paused", "Your flight is safely suspended.", "Resume flight");
  }

  #flap() {
    if (this.state !== "playing") this.#start();
    this.bird.velocity = this.settings.flapStrength;
    this.wingFrame += 1;
  }

  #frame(time) {
    if (this.state !== "playing") return;
    const elapsed = Math.min(2.2, Math.max(0.25, (time - this.lastTime) / 16.667));
    this.lastTime = time;
    this.#update(elapsed);
    this.#draw();
    if (this.state === "playing") {
      this.animationId = requestAnimationFrame((nextTime) => this.#frame(nextTime));
    }
  }

  #update(step) {
    this.bird.velocity += this.settings.gravity * step;
    this.bird.y += this.bird.velocity * step;
    this.bird.rotation = Math.max(-0.5, Math.min(1.2, this.bird.velocity * 0.08));

    const distance = this.settings.pipeSpeed * step;
    this.spawnDistance += distance;
    if (this.spawnDistance >= PIPE_SPACING) {
      this.spawnDistance = 0;
      this.#spawnPipe();
    }

    this.pipes.forEach((pipe) => {
      pipe.x -= distance;
      if (!pipe.scored && pipe.x + PIPE_WIDTH < BIRD_X) {
        pipe.scored = true;
        this.score += 1;
        this.scoreElement.textContent = this.score;
      }
    });
    this.pipes = this.pipes.filter((pipe) => pipe.x + PIPE_WIDTH > -10);

    if (this.score >= this.settings.targetScore) {
      this.#finish("won");
      return;
    }

    if (
      this.bird.y - BIRD_RADIUS <= 0 ||
      this.bird.y + BIRD_RADIUS >= HEIGHT - FLOOR_HEIGHT ||
      this.pipes.some((pipe) => this.#hitsPipe(pipe))
    ) {
      this.#finish("lost");
    }
  }

  #spawnPipe() {
    const margin = 86;
    const available = HEIGHT - FLOOR_HEIGHT - this.settings.pipeGap - margin * 2;
    const gapTop = margin + Math.random() * Math.max(1, available);
    this.pipes.push({ x: WIDTH + 20, gapTop, scored: false });
  }

  #hitsPipe(pipe) {
    const overlapsX =
      BIRD_X + BIRD_RADIUS > pipe.x &&
      BIRD_X - BIRD_RADIUS < pipe.x + PIPE_WIDTH;
    if (!overlapsX) return false;
    return (
      this.bird.y - BIRD_RADIUS < pipe.gapTop ||
      this.bird.y + BIRD_RADIUS > pipe.gapTop + this.settings.pipeGap
    );
  }

  #finish(result) {
    this.#stopAnimation();
    this.state = result;
    this.#draw();
    this.#showOverlay(
      result === "won" ? "Flight complete!" : "Bonk!",
      result === "won"
        ? `You cleared ${this.score} pipes.`
        : `Final score: ${this.score}`,
      "Fly again"
    );
  }

  #showOverlay(title, message, action) {
    this.overlayTitle.textContent = title;
    this.overlayMessage.textContent = message;
    this.actionButton.textContent = action;
    this.overlay.hidden = false;
  }

  #stopAnimation() {
    if (this.animationId !== null) cancelAnimationFrame(this.animationId);
    this.animationId = null;
  }

  #resizeCanvas() {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = WIDTH * ratio;
    this.canvas.height = HEIGHT * ratio;
    this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.#draw();
  }

  #draw() {
    if (!this.context) return;
    this.#drawSky();
    this.pipes.forEach((pipe) => this.#drawPipe(pipe));
    this.#drawGround();
    this.#drawBird();
  }

  #drawSky() {
    const palette = this.settings.skyPalette;
    const gradient = this.context.createLinearGradient(0, 0, 0, HEIGHT);
    gradient.addColorStop(0, palette.top);
    gradient.addColorStop(1, palette.bottom);
    this.context.fillStyle = gradient;
    this.context.fillRect(0, 0, WIDTH, HEIGHT);

    this.context.fillStyle = "rgba(255,255,255,0.62)";
    for (const cloud of [[58, 100, 34], [320, 160, 42], [185, 60, 25]]) {
      this.context.beginPath();
      this.context.arc(cloud[0], cloud[1], cloud[2], 0, Math.PI * 2);
      this.context.fill();
    }
  }

  #drawPipe(pipe) {
    const palette = this.settings.pipePalette;
    const bottomY = pipe.gapTop + this.settings.pipeGap;
    this.context.fillStyle = palette.fill;
    this.context.strokeStyle = palette.edge;
    this.context.lineWidth = 3;

    this.context.fillRect(pipe.x, 0, PIPE_WIDTH, pipe.gapTop);
    this.context.strokeRect(pipe.x, -2, PIPE_WIDTH, pipe.gapTop + 2);
    this.context.fillRect(pipe.x, bottomY, PIPE_WIDTH, HEIGHT - FLOOR_HEIGHT - bottomY);
    this.context.strokeRect(
      pipe.x,
      bottomY,
      PIPE_WIDTH,
      HEIGHT - FLOOR_HEIGHT - bottomY
    );

    const capHeight = 24;
    this.context.fillRect(pipe.x - 6, pipe.gapTop - capHeight, PIPE_WIDTH + 12, capHeight);
    this.context.strokeRect(
      pipe.x - 6,
      pipe.gapTop - capHeight,
      PIPE_WIDTH + 12,
      capHeight
    );
    this.context.fillRect(pipe.x - 6, bottomY, PIPE_WIDTH + 12, capHeight);
    this.context.strokeRect(pipe.x - 6, bottomY, PIPE_WIDTH + 12, capHeight);
  }

  #drawGround() {
    this.context.fillStyle = COLORS.grass;
    this.context.fillRect(0, HEIGHT - FLOOR_HEIGHT, WIDTH, 14);
    this.context.fillStyle = COLORS.ground;
    this.context.fillRect(0, HEIGHT - FLOOR_HEIGHT + 14, WIDTH, FLOOR_HEIGHT - 14);
  }

  #drawBird() {
    this.context.save();
    this.context.translate(BIRD_X, this.bird.y);
    this.context.rotate(this.bird.rotation);

    this.context.fillStyle = this.settings.birdColor;
    this.context.beginPath();
    this.context.arc(0, 0, BIRD_RADIUS, 0, Math.PI * 2);
    this.context.fill();

    this.context.fillStyle = COLORS.birdWing;
    this.context.beginPath();
    const wingY = this.wingFrame % 2 === 0 ? 5 : 9;
    this.context.ellipse(-7, wingY, 10, 6, -0.25, 0, Math.PI * 2);
    this.context.fill();

    this.context.fillStyle = "#ffffff";
    this.context.beginPath();
    this.context.arc(7, -5, 5, 0, Math.PI * 2);
    this.context.fill();
    this.context.fillStyle = COLORS.birdEye;
    this.context.beginPath();
    this.context.arc(9, -5, 2, 0, Math.PI * 2);
    this.context.fill();

    this.context.fillStyle = "#f28b30";
    this.context.beginPath();
    this.context.moveTo(13, 1);
    this.context.lineTo(24, 5);
    this.context.lineTo(13, 8);
    this.context.closePath();
    this.context.fill();
    this.context.restore();
  }

  #readSettings() {
    const sky = this.getSkyPalette();
    const pipes = this.getPipePalette();
    return {
      birdColor: this.getBirdColor() || COLORS.bird,
      skyPalette: {
        top: sky?.top || COLORS.skyTop,
        bottom: sky?.bottom || COLORS.skyBottom
      },
      pipePalette: {
        fill: pipes?.fill || COLORS.pipeFill,
        edge: pipes?.edge || COLORS.pipeEdge
      },
      gravity: this.#clamp(this.getGravity(), 0.1, 1.2, DEFAULTS.gravity),
      flapStrength: this.#clamp(
        this.getFlapStrength(),
        -14,
        -2,
        DEFAULTS.flapStrength
      ),
      pipeGap: this.#clamp(this.getPipeGap(), 95, 260, DEFAULTS.pipeGap),
      pipeSpeed: this.#clamp(this.getPipeSpeed(), 0.8, 7, DEFAULTS.pipeSpeed),
      targetScore: Math.round(
        this.#clamp(this.getTargetScore(), 1, 100, DEFAULTS.targetScore)
      )
    };
  }

  #clamp(value, minimum, maximum, fallback) {
    const number = Number(value);
    return Number.isFinite(number)
      ? Math.max(minimum, Math.min(maximum, number))
      : fallback;
  }

  #escapeText(value) {
    const element = document.createElement("span");
    element.textContent = String(value);
    return element.innerHTML;
  }

  getGameTitle() {
    return "Flappy Bird";
  }

  getGameSubtitle() {
    return "Thread the gaps. Keep flying.";
  }

  getBirdColor() {
    return COLORS.bird;
  }

  getSkyPalette() {
    return { top: COLORS.skyTop, bottom: COLORS.skyBottom };
  }

  getPipePalette() {
    return { fill: COLORS.pipeFill, edge: COLORS.pipeEdge };
  }

  getGravity() {
    return DEFAULTS.gravity;
  }

  getFlapStrength() {
    return DEFAULTS.flapStrength;
  }

  getPipeGap() {
    return DEFAULTS.pipeGap;
  }

  getPipeSpeed() {
    return DEFAULTS.pipeSpeed;
  }

  getTargetScore() {
    return DEFAULTS.targetScore;
  }
}

