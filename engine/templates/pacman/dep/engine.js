/**
 * PacMan engine - private implementation.
 *
 * Generated game files import only from ../base.js. This initial version
 * intentionally exposes no customization hooks.
 */

const COLUMNS = 21;
const ROWS = 17;
const CELL_SIZE = 28;
const STEP_MS = 135;
const STARTING_LIVES = 3;

const COLORS = {
  board: "#050711",
  wall: "#3155ff",
  wallEdge: "#7d91ff",
  pellet: "#ffe6b3",
  player: "#ffd52a",
  ghostOne: "#ff4d6d",
  ghostTwo: "#42dff5",
  eyes: "#f7fbff",
  pupils: "#17247a"
};

const DIRECTIONS = {
  up: { x: 0, y: -1, angle: -Math.PI / 2 },
  down: { x: 0, y: 1, angle: Math.PI / 2 },
  left: { x: -1, y: 0, angle: Math.PI },
  right: { x: 1, y: 0, angle: 0 }
};

export class PacManGame {
  constructor(root) {
    if (!(root instanceof HTMLElement)) {
      throw new TypeError("PacManGame requires a root HTMLElement.");
    }

    this.root = root;
    this.player = null;
    this.ghosts = [];
    this.pellets = new Set();
    this.direction = DIRECTIONS.left;
    this.queuedDirection = this.direction;
    this.score = 0;
    this.lives = this.#normalizeStartingLives(this.getStartingLives());
    this.state = "ready";
    this.timer = null;
    this.animationFrame = 0;
    this.imageCache = new Map();

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
            <div><span>Lives</span><strong data-lives>${this.lives}</strong></div>
          </div>
        </header>
        <section class="board-wrap" aria-label="PacMan game board">
          <canvas data-canvas></canvas>
          <div class="overlay" data-overlay>
            <div>
              <h2 data-overlay-title></h2>
              <p data-overlay-message></p>
              <button data-action type="button"></button>
            </div>
          </div>
        </section>
        <footer>
          <p>Arrow keys or WASD to move<br>Space to pause · R to restart</p>
          <div class="direction-pad" aria-label="Direction controls">
            <button data-direction="up" aria-label="Move up">↑</button>
            <button data-direction="left" aria-label="Move left">←</button>
            <button data-direction="down" aria-label="Move down">↓</button>
            <button data-direction="right" aria-label="Move right">→</button>
          </div>
        </footer>
      </main>
    `;

    this.canvas = this.root.querySelector("[data-canvas]");
    this.context = this.canvas.getContext("2d");
    this.scoreElement = this.root.querySelector("[data-score]");
    this.livesElement = this.root.querySelector("[data-lives]");
    this.overlay = this.root.querySelector("[data-overlay]");
    this.overlayTitle = this.root.querySelector("[data-overlay-title]");
    this.overlayMessage = this.root.querySelector("[data-overlay-message]");
    this.actionButton = this.root.querySelector("[data-action]");

    document.documentElement.style.setProperty(
      "--board-ratio",
      `${COLUMNS} / ${ROWS}`
    );
    this.#bindEvents();
    this.#resizeCanvas();
  }

  #bindEvents() {
    this.actionButton.addEventListener("click", () => this.#start());
    this.root.querySelectorAll("[data-direction]").forEach((button) => {
      button.addEventListener("pointerdown", () => {
        this.#setDirection(button.dataset.direction);
      });
    });

    document.addEventListener("keydown", (event) => {
      const keys = {
        ArrowUp: "up", w: "up", W: "up",
        ArrowDown: "down", s: "down", S: "down",
        ArrowLeft: "left", a: "left", A: "left",
        ArrowRight: "right", d: "right", D: "right"
      };

      if (keys[event.key]) {
        event.preventDefault();
        this.#setDirection(keys[event.key]);
      } else if (event.code === "Space") {
        event.preventDefault();
        this.#togglePause();
      } else if (event.key === "r" || event.key === "R") {
        this.#resetGame();
        this.#start();
      }
    });

    window.addEventListener("resize", () => this.#resizeCanvas());
    document.addEventListener("visibilitychange", () => {
      if (document.hidden && this.state === "playing") this.#togglePause();
    });
  }

  #resetGame() {
    this.#stopTimer();
    this.score = 0;
    this.lives = this.#normalizeStartingLives(this.getStartingLives());
    this.scoreElement.textContent = "0";
    this.livesElement.textContent = this.lives;
    this.#createPellets();
    this.#resetActors();
    this.state = "ready";
    this.#showOverlay("start");
    this.#draw();
  }

  #resetActors() {
    const ghostColors = this.getGhostColors();
    this.player = { x: 10, y: 14 };
    this.ghosts = [
      {
        x: 10,
        y: 8,
        color: ghostColors[0] || COLORS.ghostOne,
        direction: DIRECTIONS.left
      },
      {
        x: 10,
        y: 7,
        color: ghostColors[1] || ghostColors[0] || COLORS.ghostTwo,
        direction: DIRECTIONS.right
      }
    ];
    this.direction = DIRECTIONS.left;
    this.queuedDirection = this.direction;
    this.pellets.delete(this.#cellKey(this.player.x, this.player.y));
    this.ghosts.forEach((ghost) => {
      this.pellets.delete(this.#cellKey(ghost.x, ghost.y));
    });
  }

  #createPellets() {
    this.pellets.clear();
    for (let y = 0; y < ROWS; y += 1) {
      for (let x = 0; x < COLUMNS; x += 1) {
        if (!this.#isWall(x, y)) this.pellets.add(this.#cellKey(x, y));
      }
    }
  }

  #start() {
    if (this.state === "won" || this.state === "lost") this.#resetGame();
    this.state = "playing";
    this.overlay.hidden = true;
    this.#scheduleTick();
  }

  #togglePause() {
    if (this.state === "playing") {
      this.state = "paused";
      this.#stopTimer();
      this.#showOverlay("pause");
    } else if (this.state === "paused" || this.state === "ready") {
      this.#start();
    }
  }

  #setDirection(name) {
    const inverted = {
      up: "down",
      down: "up",
      left: "right",
      right: "left"
    };
    const controlName = this.getControlMode(this.score, this.lives) === "inverted"
      ? inverted[name]
      : name;
    this.queuedDirection = DIRECTIONS[controlName];
    if (this.state === "ready") this.#start();
  }

  #tick() {
    if (this.state !== "playing") return;

    const queuedTarget = {
      x: this.player.x + this.queuedDirection.x,
      y: this.player.y + this.queuedDirection.y
    };
    if (!this.#isWall(queuedTarget.x, queuedTarget.y)) {
      this.direction = this.queuedDirection;
    }

    const next = {
      x: this.player.x + this.direction.x,
      y: this.player.y + this.direction.y
    };
    if (!this.#isWall(next.x, next.y)) this.player = next;

    if (this.#isHazard(this.player.x, this.player.y)) {
      this.#loseLife();
      return;
    }

    const pelletKey = this.#cellKey(this.player.x, this.player.y);
    if (this.pellets.delete(pelletKey)) {
      this.score += this.#normalizePelletScoreValue(this.getPelletScoreValue(this.score));
      this.scoreElement.textContent = this.score;
    }

    this.#moveGhosts();
    if (this.#ghostCaughtPlayer()) {
      this.#loseLife();
      return;
    }

    if (this.pellets.size === 0) {
      this.#finish("won");
      return;
    }

    this.animationFrame += 1;
    this.#draw();
    this.#scheduleTick();
  }

  #moveGhosts() {
    this.ghosts.forEach((ghost) => {
      const choices = Object.values(DIRECTIONS).filter((direction) => {
        const x = ghost.x + direction.x;
        const y = ghost.y + direction.y;
        return !this.#isWall(x, y);
      });
      const forwardChoices = choices.filter(
        (direction) =>
          direction.x + ghost.direction.x !== 0 ||
          direction.y + ghost.direction.y !== 0
      );
      const candidates = forwardChoices.length ? forwardChoices : choices;
      candidates.sort((a, b) => {
        const distanceA =
          Math.abs(ghost.x + a.x - this.player.x) +
          Math.abs(ghost.y + a.y - this.player.y);
        const distanceB =
          Math.abs(ghost.x + b.x - this.player.x) +
          Math.abs(ghost.y + b.y - this.player.y);
        return distanceA - distanceB;
      });

      const chaseProbability = Math.max(
        0,
        Math.min(1, Number(this.getGhostChaseProbability()) || 0)
      );
      const chase = Math.random() < chaseProbability;
      ghost.direction = chase
        ? candidates[0]
        : candidates[Math.floor(Math.random() * candidates.length)];
      ghost.x += ghost.direction.x;
      ghost.y += ghost.direction.y;
    });
  }

  #ghostCaughtPlayer() {
    return this.ghosts.some(
      (ghost) => ghost.x === this.player.x && ghost.y === this.player.y
    );
  }

  #isHazard(x, y) {
    return this.#getHazardCells().some((cell) => cell.x === x && cell.y === y);
  }

  #loseLife() {
    this.#stopTimer();
    this.lives -= 1;
    this.livesElement.textContent = this.lives;

    if (this.lives <= 0) {
      this.#finish("lost");
      return;
    }

    this.#resetActors();
    this.state = "ready";
    this.#draw();
    this.#showOverlay("caught", { lives: this.lives });
  }

  #finish(result) {
    this.#stopTimer();
    this.state = result;
    this.#draw();
    this.#showOverlay(result, { score: this.score });
  }

  #scheduleTick() {
    this.#stopTimer();
    const requestedDelay = Number(this.getStepDelay());
    const delay = Math.max(
      40,
      Math.min(500, Number.isFinite(requestedDelay) ? requestedDelay : STEP_MS)
    );
    this.timer = window.setTimeout(() => this.#tick(), delay);
  }

  #stopTimer() {
    if (this.timer !== null) window.clearTimeout(this.timer);
    this.timer = null;
  }

  #isWall(x, y) {
    if (x < 0 || y < 0 || x >= COLUMNS || y >= ROWS) return true;
    if (x === 0 || y === 0 || x === COLUMNS - 1 || y === ROWS - 1) return true;

    const verticalBar =
      x % 4 === 0 && y >= 3 && y <= ROWS - 4 && y !== 8;
    const horizontalBar =
      y % 4 === 0 && x >= 3 && x <= COLUMNS - 4 && x !== 10;
    return verticalBar || horizontalBar;
  }

  #showOverlay(mode, context = {}) {
    const content = this.getOverlayContent(mode, context);
    this.overlayTitle.textContent = content.title;
    this.overlayMessage.textContent = content.message;
    this.actionButton.textContent = content.action;
    this.overlay.hidden = false;
  }

  #resizeCanvas() {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = COLUMNS * CELL_SIZE * ratio;
    this.canvas.height = ROWS * CELL_SIZE * ratio;
    this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.#draw();
  }

  #draw() {
    if (!this.player) return;

    this.context.fillStyle = this.getBoardBackgroundColor();
    this.context.fillRect(0, 0, COLUMNS * CELL_SIZE, ROWS * CELL_SIZE);

    for (let y = 0; y < ROWS; y += 1) {
      for (let x = 0; x < COLUMNS; x += 1) {
        if (this.#isWall(x, y)) this.#drawWall(x, y);
      }
    }

    this.pellets.forEach((key) => {
      const [x, y] = key.split(":").map(Number);
      const style = this.getPelletStyle();
      const radius = Math.max(1, Math.min(CELL_SIZE * 0.35, Number(style.radius) || 2.5));
      this.context.fillStyle = style.color || COLORS.pellet;
      this.context.beginPath();
      this.context.arc(
        x * CELL_SIZE + CELL_SIZE / 2,
        y * CELL_SIZE + CELL_SIZE / 2,
        radius,
        0,
        Math.PI * 2
      );
      this.context.fill();
    });

    this.#getHazardCells().forEach((cell) => this.#drawHazard(cell));

    this.#drawPlayer();
    const ghostImages = this.getGhostImageUrls();
    this.ghosts.forEach((ghost, index) => this.#drawGhost(ghost, ghostImages[index]));
  }

  #drawWall(x, y) {
    const inset = 2;
    const palette = this.getWallPalette();
    this.context.fillStyle = palette.fill || COLORS.wall;
    this.context.beginPath();
    this.context.roundRect(
      x * CELL_SIZE + inset,
      y * CELL_SIZE + inset,
      CELL_SIZE - inset * 2,
      CELL_SIZE - inset * 2,
      6
    );
    this.context.fill();
    this.context.strokeStyle = palette.edge || COLORS.wallEdge;
    this.context.lineWidth = 1;
    this.context.stroke();
  }

  #drawPlayer() {
    const centerX = this.player.x * CELL_SIZE + CELL_SIZE / 2;
    const centerY = this.player.y * CELL_SIZE + CELL_SIZE / 2;
    const imageUrl = this.getPlayerImageUrl();
    const image = imageUrl ? this.#loadImage(imageUrl) : null;

    if (image?.complete && image.naturalWidth > 0) {
      this.#drawCellImage(this.player.x, this.player.y, image);
      return;
    }

    const mouth = this.animationFrame % 2 === 0 ? 0.2 : 0.08;
    const angle = this.direction.angle;

    this.context.fillStyle = this.getPlayerColor();
    this.context.beginPath();
    this.context.moveTo(centerX, centerY);
    this.context.arc(
      centerX,
      centerY,
      CELL_SIZE * 0.4,
      angle + mouth * Math.PI,
      angle + (2 - mouth) * Math.PI
    );
    this.context.closePath();
    this.context.fill();
  }

  #drawGhost(ghost, imageUrl = null) {
    const image = imageUrl ? this.#loadImage(imageUrl) : null;
    if (image?.complete && image.naturalWidth > 0) {
      this.#drawCellImage(ghost.x, ghost.y, image);
      return;
    }

    const x = ghost.x * CELL_SIZE + 4;
    const y = ghost.y * CELL_SIZE + 4;
    const size = CELL_SIZE - 8;

    this.context.fillStyle = ghost.color;
    this.context.beginPath();
    this.context.roundRect(x, y, size, size, [size / 2, size / 2, 3, 3]);
    this.context.fill();

    this.context.fillStyle = COLORS.eyes;
    this.context.beginPath();
    this.context.arc(x + size * 0.35, y + size * 0.42, 3.2, 0, Math.PI * 2);
    this.context.arc(x + size * 0.67, y + size * 0.42, 3.2, 0, Math.PI * 2);
    this.context.fill();

    this.context.fillStyle = COLORS.pupils;
    this.context.beginPath();
    this.context.arc(x + size * 0.37, y + size * 0.44, 1.5, 0, Math.PI * 2);
    this.context.arc(x + size * 0.69, y + size * 0.44, 1.5, 0, Math.PI * 2);
    this.context.fill();
  }

  #cellKey(x, y) {
    return `${x}:${y}`;
  }

  getGameTitle() {
    return "PacMan";
  }

  getGameSubtitle() {
    return "Clear the maze. Outsmart the ghosts.";
  }

  getPlayerColor() {
    return COLORS.player;
  }

  getPlayerImageUrl() {
    return null;
  }

  getGhostColors() {
    return [COLORS.ghostOne, COLORS.ghostTwo];
  }

  getGhostImageUrls() {
    return [];
  }

  getBoardBackgroundColor() {
    return COLORS.board;
  }

  getWallPalette() {
    return { fill: COLORS.wall, edge: COLORS.wallEdge };
  }

  getPelletStyle() {
    return { color: COLORS.pellet, radius: 2.5 };
  }

  getStepDelay() {
    return STEP_MS;
  }

  getControlMode(_score, _lives) {
    return "normal";
  }

  getPelletScoreValue(_score) {
    return 10;
  }

  getHazardCells(_score) {
    return [];
  }

  getHazardColor(_score) {
    return "#ff3d71";
  }

  getStartingLives() {
    return STARTING_LIVES;
  }

  getGhostChaseProbability() {
    return 0.72;
  }

  getOverlayContent(mode, context = {}) {
    const lives = Number(context.lives) || 0;
    return {
      start: {
        title: "Ready?",
        message: "Eat every pellet and avoid the ghosts.",
        action: "Start game"
      },
      pause: {
        title: "Paused",
        message: "The maze is holding still.",
        action: "Resume"
      },
      caught: {
        title: "Caught!",
        message: `${lives} ${lives === 1 ? "life" : "lives"} remaining.`,
        action: "Keep going"
      },
      won: {
        title: "Maze cleared!",
        message: `Final score: ${Number(context.score) || 0}`,
        action: "Play again"
      },
      lost: {
        title: "Game over",
        message: "The ghosts got you.",
        action: "Play again"
      }
    }[mode];
  }

  #escapeText(value) {
    const element = document.createElement("span");
    element.textContent = String(value);
    return element.innerHTML;
  }

  #drawHazard(cell) {
    const x = cell.x * CELL_SIZE;
    const y = cell.y * CELL_SIZE;
    this.context.fillStyle = this.getHazardColor(this.score);
    this.context.beginPath();
    this.context.roundRect(x + 5, y + 5, CELL_SIZE - 10, CELL_SIZE - 10, 4);
    this.context.fill();

    this.context.strokeStyle = "rgba(255, 255, 255, 0.55)";
    this.context.lineWidth = 2;
    this.context.beginPath();
    this.context.moveTo(x + 10, y + 10);
    this.context.lineTo(x + CELL_SIZE - 10, y + CELL_SIZE - 10);
    this.context.moveTo(x + CELL_SIZE - 10, y + 10);
    this.context.lineTo(x + 10, y + CELL_SIZE - 10);
    this.context.stroke();
    this.context.lineWidth = 1;
  }

  #drawCellImage(cellX, cellY, image) {
    const inset = 2;
    const size = CELL_SIZE - inset * 2;
    const sourceSize = Math.min(image.naturalWidth, image.naturalHeight);
    const sourceX = (image.naturalWidth - sourceSize) / 2;
    const sourceY = (image.naturalHeight - sourceSize) / 2;

    this.context.drawImage(
      image,
      sourceX,
      sourceY,
      sourceSize,
      sourceSize,
      cellX * CELL_SIZE + inset,
      cellY * CELL_SIZE + inset,
      size,
      size
    );
  }

  #loadImage(url) {
    if (this.imageCache.has(url)) {
      return this.imageCache.get(url);
    }

    const image = new Image();
    image.addEventListener("load", () => this.#draw(), { once: true });
    image.src = url;
    this.imageCache.set(url, image);
    return image;
  }

  #getHazardCells() {
    const cells = this.getHazardCells(this.score);
    if (!Array.isArray(cells)) return [];

    const seen = new Set();
    return cells.flatMap((cell) => {
      const x = Math.floor(Number(cell?.x));
      const y = Math.floor(Number(cell?.y));
      const key = `${x},${y}`;
      if (
        !Number.isFinite(x) ||
        !Number.isFinite(y) ||
        this.#isWall(x, y) ||
        seen.has(key)
      ) {
        return [];
      }
      seen.add(key);
      return [{ x, y }];
    });
  }

  #normalizePelletScoreValue(value) {
    const scoreValue = Math.floor(Number(value));
    return Number.isFinite(scoreValue) ? Math.max(1, Math.min(100, scoreValue)) : 10;
  }

  #normalizeStartingLives(value) {
    const lives = Math.floor(Number(value));
    return Number.isFinite(lives) ? Math.max(1, Math.min(9, lives)) : STARTING_LIVES;
  }
}
