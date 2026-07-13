/**
 * Snake engine — internal implementation.
 *
 * This file (and everything else in dep/) is the private Snake engine.
 * It is NOT the contract. Generated game.js files should never import
 * from here directly — they extend the class re-exported by ../base.js.
 *
 * All hardcoded settings live here. Customization hooks are added
 * iteratively per engine/template_workflow.md.
 */

const COLUMNS = 20;
const ROWS = 16;
const CELL_SIZE = 28;
const INITIAL_LENGTH = 4;
const SPEED_MS = 120;
const SPEED_INCREASE_PER_FOOD_MS = 3;
const MINIMUM_SPEED_MS = 60;
const TARGET_SCORE = 10;

const COLORS = {
  boardBackground: "#0d1928",
  gridColor: "#17283a",
  snakeBody: "#62e6a7",
  snakeHead: "#d8fff0",
  food: "#ffcf5a",
  obstacle: "#ef476f"
};

export class SnakeGame {
  constructor(root) {
    if (!(root instanceof HTMLElement)) {
      throw new TypeError("SnakeGame requires a root HTMLElement.");
    }
    this.root = root;
    this.board = this.#normalizeBoardDimensions(this.getBoardDimensions());
    this.snake = [];
    this.food = null;
    this.direction = { x: 1, y: 0 };
    this.queuedDirection = this.direction;
    this.score = 0;
    this.state = "ready";
    this.timer = null;
    this.snakeCellImageCache = new Map();

    this.renderShell();
    this.reset();
  }

  renderShell() {
    const title = this.getGameTitle();
    const subtitle = this.getGameSubtitle();
    const targetScore = this.getTargetScore();
    document.title = title;

    this.root.innerHTML = `
      <main class="game-shell">
        <header class="game-header">
          <div>
            <h1>${this.#escapeText(title)}</h1>
            <p class="subtitle">${this.#escapeText(subtitle)}</p>
          </div>
          <div class="scoreboard" aria-label="Game score">
            <div class="score"><span>Score</span><strong data-score>0</strong></div>
            <div class="score"><span>Target</span><strong>${targetScore}</strong></div>
          </div>
        </header>
        <section class="board-wrap" aria-label="Snake game board">
          <canvas data-canvas></canvas>
          <div class="overlay" data-overlay>
            <div>
              <h2 data-overlay-title></h2>
              <p data-overlay-message></p>
              <button data-action type="button"></button>
            </div>
          </div>
        </section>
        <footer class="controls">
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
    this.overlay = this.root.querySelector("[data-overlay]");
    this.overlayTitle = this.root.querySelector("[data-overlay-title]");
    this.overlayMessage = this.root.querySelector("[data-overlay-message]");
    this.actionButton = this.root.querySelector("[data-action]");

    document.documentElement.style.setProperty(
      "--board-ratio",
      `${this.board.columns} / ${this.board.rows}`
    );
    this.bindEvents();
    this.resizeCanvas();
  }

  bindEvents() {
    this.actionButton.addEventListener("click", () => this.start());
    this.root.querySelectorAll("[data-direction]").forEach((button) => {
      button.addEventListener("pointerdown", () => {
        this.setDirection(button.dataset.direction);
      });
    });

    document.addEventListener("keydown", (event) => this.handleKey(event));
    window.addEventListener("resize", () => this.resizeCanvas());
    document.addEventListener("visibilitychange", () => {
      if (document.hidden && this.state === "playing") this.pause();
    });
  }

  handleKey(event) {
    const keys = {
      ArrowUp: "up", w: "up", W: "up",
      ArrowDown: "down", s: "down", S: "down",
      ArrowLeft: "left", a: "left", A: "left",
      ArrowRight: "right", d: "right", D: "right"
    };
    if (keys[event.key]) {
      event.preventDefault();
      this.setDirection(keys[event.key]);
    } else if (event.code === "Space") {
      event.preventDefault();
      this.pause();
    } else if (event.key === "r" || event.key === "R") {
      this.reset();
      this.start();
    }
  }

  reset() {
    this.stopTimer();
    this.score = 0;
    this.scoreElement.textContent = "0";
    this.direction = { x: 1, y: 0 };
    this.queuedDirection = this.direction;

    const centerX = Math.floor(this.board.columns / 2);
    const centerY = Math.floor(this.board.rows / 2);
    this.snake = Array.from(
      { length: INITIAL_LENGTH },
      (_, index) => ({ x: centerX - index, y: centerY })
    );
    this.food = this.createFood();
    this.state = "ready";
    this.showOverlay("start");
    this.draw();
  }

  start() {
    if (this.state === "won" || this.state === "lost") this.reset();
    this.state = "playing";
    this.overlay.hidden = true;
    this.scheduleTick();
  }

  pause() {
    if (this.state === "playing") {
      this.state = "paused";
      this.stopTimer();
      this.showOverlay("pause");
    } else if (this.state === "paused" || this.state === "ready") {
      this.start();
    }
  }

  setDirection(name) {
    const directions = {
      up: { x: 0, y: -1 },
      down: { x: 0, y: 1 },
      left: { x: -1, y: 0 },
      right: { x: 1, y: 0 }
    };
    const inverted = {
      up: "down",
      down: "up",
      left: "right",
      right: "left"
    };
    const controlName = this.getControlMode(this.score) === "inverted"
      ? inverted[name]
      : name;
    const next = directions[controlName];
    if (next.x + this.direction.x !== 0 || next.y + this.direction.y !== 0) {
      this.queuedDirection = next;
    }
    if (this.state === "ready") this.start();
  }

  tick() {
    if (this.state !== "playing") return;
    this.direction = this.queuedDirection;
    const head = this.snake[0];
    let next = { x: head.x + this.direction.x, y: head.y + this.direction.y };

    if (this.getWallMode() === "wrap") {
      next = {
        x: (next.x + this.board.columns) % this.board.columns,
        y: (next.y + this.board.rows) % this.board.rows
      };
    }

    if (this.hasCollision(next)) {
      this.finish("lost");
      return;
    }

    this.snake.unshift(next);
    if (this.food && next.x === this.food.x && next.y === this.food.y) {
      this.score += this.#normalizeFoodScoreValue(this.getFoodScoreValue(this.score));
      this.scoreElement.textContent = this.score;
      if (this.score >= this.getTargetScore()) {
        this.finish("won");
        return;
      }
      this.food = this.createFood();
    } else {
      this.snake.pop();
    }

    this.draw();
    this.scheduleTick();
  }

  hasCollision(head) {
    if (
      this.getWallMode() === "solid" &&
      (
        head.x < 0 ||
        head.y < 0 ||
        head.x >= this.board.columns ||
        head.y >= this.board.rows
      )
    ) {
      return true;
    }
    return (
      this.snake.some((part) => part.x === head.x && part.y === head.y) ||
      this.#getObstacleCells().some((cell) => cell.x === head.x && cell.y === head.y)
    );
  }

  createFood() {
    const open = [];
    for (let y = 0; y < this.board.rows; y += 1) {
      for (let x = 0; x < this.board.columns; x += 1) {
        if (!this.snake.some((part) => part.x === x && part.y === y)) {
          open.push({ x, y });
        }
      }
    }
    const obstacles = this.#getObstacleCells();
    const filtered = open.filter((cell) => (
      !obstacles.some((obstacle) => obstacle.x === cell.x && obstacle.y === cell.y)
    ));
    return filtered[Math.floor(Math.random() * filtered.length)] || null;
  }

  finish(result) {
    this.state = result;
    this.stopTimer();
    this.draw();
    this.showOverlay(result);
  }

  scheduleTick() {
    this.stopTimer();
    const requestedDelay = Number(this.getMoveDelay(this.score));
    const delay = Math.max(16, Number.isFinite(requestedDelay) ? requestedDelay : SPEED_MS);
    this.timer = window.setTimeout(() => this.tick(), delay);
  }

  stopTimer() {
    if (this.timer !== null) window.clearTimeout(this.timer);
    this.timer = null;
  }

  showOverlay(mode) {
    const content = this.getOverlayContent(mode);
    this.overlayTitle.textContent = content.title;
    this.overlayMessage.textContent = content.message;
    this.actionButton.textContent = content.action;
    this.overlay.hidden = false;
  }

  resizeCanvas() {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = this.board.columns * CELL_SIZE * ratio;
    this.canvas.height = this.board.rows * CELL_SIZE * ratio;
    this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.draw();
  }

  draw() {
    if (!this.snake.length) return;
    this.context.fillStyle = this.getBoardBackgroundColor();
    this.context.fillRect(
      0,
      0,
      this.board.columns * CELL_SIZE,
      this.board.rows * CELL_SIZE
    );

    this.context.strokeStyle = this.getGridColor();
    this.context.beginPath();
    for (let x = 1; x < this.board.columns; x += 1) {
      this.context.moveTo(x * CELL_SIZE + 0.5, 0);
      this.context.lineTo(
        x * CELL_SIZE + 0.5,
        this.board.rows * CELL_SIZE
      );
    }
    for (let y = 1; y < this.board.rows; y += 1) {
      this.context.moveTo(0, y * CELL_SIZE + 0.5);
      this.context.lineTo(
        this.board.columns * CELL_SIZE,
        y * CELL_SIZE + 0.5
      );
    }
    this.context.stroke();

    this.#getObstacleCells().forEach((cell) => this.#drawObstacle(cell));

    if (this.food) this.#drawFood();

    this.snake.forEach((part, index) => {
      const imageUrl = this.getSnakeCellImage(index, this.snake.length);
      const image = imageUrl ? this.#loadSnakeCellImage(imageUrl) : null;

      if (image?.complete && image.naturalWidth > 0) {
        this.#drawSnakeCellImage(part, image);
      } else {
        this.#drawCell(
          part,
          this.getSnakeCellColor(index, this.snake.length),
          index === 0 ? 6 : 5
        );
      }
    });
  }

  getSnakeCellColor(index, _total) {
    return index === 0 ? COLORS.snakeHead : COLORS.snakeBody;
  }

  getSnakeCellImage(_index, _total) {
    return null;
  }

  getGameTitle() {
    return "Snake";
  }

  getGameSubtitle() {
    return "Collect the food and keep moving.";
  }

  getMoveDelay(score) {
    return Math.max(
      MINIMUM_SPEED_MS,
      SPEED_MS - score * SPEED_INCREASE_PER_FOOD_MS
    );
  }

  getTargetScore() {
    return TARGET_SCORE;
  }

  getBoardBackgroundColor() {
    return COLORS.boardBackground;
  }

  getGridColor() {
    return COLORS.gridColor;
  }

  getFoodColor() {
    return COLORS.food;
  }

  getFoodShape() {
    return "circle";
  }

  getFoodEmoji() {
    return null;
  }

  getWallMode() {
    return "solid";
  }

  getControlMode(_score) {
    return "normal";
  }

  getFoodScoreValue(_score) {
    return 1;
  }

  getObstacleCells(_score, _board) {
    return [];
  }

  getObstacleColor(_score) {
    return COLORS.obstacle;
  }

  getBoardDimensions() {
    return { columns: COLUMNS, rows: ROWS };
  }

  getOverlayContent(mode) {
    return {
      start: {
        title: "Ready?",
        message: "Use the arrow keys or WASD to move.",
        action: "Start game"
      },
      pause: {
        title: "Paused",
        message: "The board will wait.",
        action: "Resume"
      },
      won: {
        title: "You win",
        message: "Target reached.",
        action: "Play again"
      },
      lost: {
        title: "Game over",
        message: "Try another route.",
        action: "Play again"
      }
    }[mode];
  }

  #drawFood() {
    const x = this.food.x * CELL_SIZE + CELL_SIZE / 2;
    const y = this.food.y * CELL_SIZE + CELL_SIZE / 2;
    const emoji = this.getFoodEmoji();

    if (emoji) {
      this.context.font = `${CELL_SIZE * 0.78}px system-ui, sans-serif`;
      this.context.textAlign = "center";
      this.context.textBaseline = "middle";
      this.context.fillText(emoji, x, y + 1);
      return;
    }

    const shape = this.getFoodShape();
    const size = CELL_SIZE * 0.56;
    this.context.fillStyle = this.getFoodColor();
    this.context.beginPath();

    if (shape === "square") {
      this.context.roundRect(x - size / 2, y - size / 2, size, size, 3);
    } else if (shape === "diamond") {
      this.context.moveTo(x, y - size / 1.8);
      this.context.lineTo(x + size / 1.8, y);
      this.context.lineTo(x, y + size / 1.8);
      this.context.lineTo(x - size / 1.8, y);
      this.context.closePath();
    } else {
      this.context.arc(x, y, size / 2, 0, Math.PI * 2);
    }
    this.context.fill();
  }

  #drawObstacle(cell) {
    const x = cell.x * CELL_SIZE;
    const y = cell.y * CELL_SIZE;
    this.context.fillStyle = this.getObstacleColor(this.score);
    this.context.beginPath();
    this.context.roundRect(x + 4, y + 4, CELL_SIZE - 8, CELL_SIZE - 8, 4);
    this.context.fill();

    this.context.strokeStyle = "rgba(255, 255, 255, 0.48)";
    this.context.lineWidth = 2;
    this.context.beginPath();
    this.context.moveTo(x + 9, y + 9);
    this.context.lineTo(x + CELL_SIZE - 9, y + CELL_SIZE - 9);
    this.context.moveTo(x + CELL_SIZE - 9, y + 9);
    this.context.lineTo(x + 9, y + CELL_SIZE - 9);
    this.context.stroke();
    this.context.lineWidth = 1;
  }

  #escapeText(value) {
    const element = document.createElement("span");
    element.textContent = String(value);
    return element.innerHTML;
  }

  #loadSnakeCellImage(url) {
    if (this.snakeCellImageCache.has(url)) {
      return this.snakeCellImageCache.get(url);
    }

    const image = new Image();
    image.addEventListener("load", () => this.draw(), { once: true });
    image.src = url;
    this.snakeCellImageCache.set(url, image);
    return image;
  }

  #drawSnakeCellImage(cell, image) {
    const inset = 1;
    const targetSize = CELL_SIZE - inset * 2;
    const sourceSize = Math.min(image.naturalWidth, image.naturalHeight);
    const sourceX = (image.naturalWidth - sourceSize) / 2;
    const sourceY = (image.naturalHeight - sourceSize) / 2;

    this.context.drawImage(
      image,
      sourceX,
      sourceY,
      sourceSize,
      sourceSize,
      cell.x * CELL_SIZE + inset,
      cell.y * CELL_SIZE + inset,
      targetSize,
      targetSize
    );
  }

  #drawCell(cell, color, radius) {
    this.context.fillStyle = color;
    this.context.beginPath();
    this.context.roundRect(
      cell.x * CELL_SIZE + 2,
      cell.y * CELL_SIZE + 2,
      CELL_SIZE - 4,
      CELL_SIZE - 4,
      radius
    );
    this.context.fill();
  }

  #getObstacleCells() {
    const cells = this.getObstacleCells(this.score, {
      columns: this.board.columns,
      rows: this.board.rows
    });
    if (!Array.isArray(cells)) return [];

    const seen = new Set();
    return cells.flatMap((cell) => {
      const x = Math.floor(Number(cell?.x));
      const y = Math.floor(Number(cell?.y));
      const key = `${x},${y}`;
      if (
        !Number.isFinite(x) ||
        !Number.isFinite(y) ||
        x < 0 ||
        y < 0 ||
        x >= this.board.columns ||
        y >= this.board.rows ||
        seen.has(key)
      ) {
        return [];
      }
      seen.add(key);
      return [{ x, y }];
    });
  }

  #normalizeFoodScoreValue(value) {
    const scoreValue = Math.floor(Number(value));
    return Number.isFinite(scoreValue) ? Math.max(1, Math.min(5, scoreValue)) : 1;
  }

  #normalizeBoardDimensions(dimensions) {
    const columns = Math.floor(Number(dimensions?.columns));
    const rows = Math.floor(Number(dimensions?.rows));
    return {
      columns: Number.isFinite(columns) ? Math.max(6, Math.min(60, columns)) : COLUMNS,
      rows: Number.isFinite(rows) ? Math.max(6, Math.min(60, rows)) : ROWS
    };
  }
}
