# KAPLAY API REFERENCE (STRICT)

## CRITICAL INSTRUCTION FOR AI AGENT

You are writing JavaScript for Kaplay (formerly Kaboom.js).

**RULE:** Do NOT invent classes (e.g., `class Player extends GameObject`). Kaplay uses a strict, functional Entity-Component System (ECS). You must compose objects using `k.add([...components])`. Do not invent methods that are not on this list.

Kaplay is loaded globally via `<script>` tag. The `kaplay` function is available on `window`.
All game code uses ES modules (`import`/`export`). `index.html` loads `main.js` as `<script type="module">`.

---

## 1. Initialization

In `main.js` (the entry point loaded by `index.html`):

```js
// kaplay is a global from the <script> tag — no import needed
const k = kaplay({
  width: 800,
  height: 600,
  background: [0, 0, 0],
});
// Do NOT export k — pass it as argument to other modules instead
```

Other files receive `k` as a function argument (passed by main.js) and export their setup functions:

```js
// scenes.js — receives k from main.js, does NOT import it
export function registerScenes(k) {
  k.scene("game", () => { /* ... */ });
}
```

In main.js:
```js
import { registerScenes } from "./scenes.js";

const k = kaplay({ width: 800, height: 600, background: [0, 0, 0] });
registerScenes(k);
k.go("game");
```

**Do NOT** `import k from "./main.js"` — this creates circular imports.

---

## 2. Loading Assets & Animations

Must be done before using them in scenes.

```js
k.loadSprite("sprite_name", "path/to/image.png");

k.loadSprite("hero", "sprites/hero.png", {
  sliceX: 5,        // 5 frames horizontally
  sliceY: 1,        // 1 frame vertically
  anims: {
    idle: { from: 0, to: 0 },
    run: { from: 1, to: 4, loop: true, speed: 10 },
  },
});

k.loadSound("jump", "sounds/jump.mp3");
```

**Playing animations and sounds:**

```js
const player = k.add([k.sprite("hero"), k.pos(100, 100)]);
player.play("run");                    // Play a sprite animation
k.play("jump", { volume: 0.5 });      // Play a sound with options
```

---

## 3. Creating Entities (The `add` function)

Entities are built by passing an array of component functions to `k.add()`.

```js
const player = k.add([
  k.sprite("hero"),       // Renders a loaded sprite
  k.pos(100, 100),        // X, Y position
  k.area(),               // Generates a collision hitbox based on the sprite
  k.body(),               // Reacts to gravity and physics
  k.anchor("center"),     // Sets the origin point to the center
  "player_tag",           // Raw strings become tags for collision routing
]);
```

---

## 4. Built-in Visual & Transform Components

Pass these into the `k.add([...])` array:

- `k.pos(x, y)` — Position.
- `k.scale(x, y)` or `k.scale(number)` — Scaling.
- `k.rotate(angle)` — Rotation in degrees.
- `k.color(r, g, b)` — RGB tinting (0-255). **ONLY accepts three numbers.** Never pass hex strings, CSS color names, or constants like `k.BLACK`.
- `k.opacity(0.0 to 1.0)` — Alpha transparency.
- `k.sprite("name", { anim: "run" })` — Draws a loaded image.
- `k.rect(width, height)` — Draws a rectangle.
- `k.circle(radius)` — Draws a circle.
- `k.text("string", { size: 24, font: "sans-serif" })` — Draws text.
- `k.anchor("center")` — Sets the origin/anchor point.

---

## 5. Physics & Collision Components

Pass these into the `k.add([...])` array:

- `k.area()` — Adds a hitbox based on the visual shape.
- `k.area({ shape: new k.Rect(k.vec2(0), 32, 32) })` — Custom hitbox.
- `k.body()` — Makes an object physical (affected by gravity).
- `k.body({ isStatic: true })` — Static objects don't fall but block other bodies.
- `k.body({ jumpForce: 600 })` — Configures jump force.

**Global Physics:**

```js
k.setGravity(1600);  // Sets global gravity on the Y-axis
```

---

## 6. Object Methods (on the returned `k.add()` object)

```js
obj.move(x, y)              // Continuous speed (pixels per second)
obj.jump(force)             // Makes a body() jump
obj.isGrounded()            // Boolean: is body() touching the floor?
obj.play("animName")        // Plays a sprite animation
obj.destroy()               // Removes the object from the game
obj.pos.x / obj.pos.y      // Read or modify coordinates (requires pos())
```

**Per-object event handlers:**

```js
obj.onCollide("tag", (other) => { ... });  // On collision with tagged object
obj.onUpdate(() => { ... });               // Runs every frame for this object
```

---

## 7. Global Input & Events

```js
k.onKeyDown("left", () => { ... });    // Every frame the key is held
k.onKeyPress("space", () => { ... });  // Once when key is pressed
k.onMousePress(() => { ... });         // On mouse click
k.mousePos()                           // Returns Vec2 of mouse coordinates
k.onUpdate(() => { ... });             // Global update loop (every frame)
k.onCollide("tag1", "tag2", (a, b) => { ... });  // Global collision resolver
```

---

## 8. Custom Components (MANDATORY FOR CUSTOM LOGIC)

To create modular logic, write a pure function that returns a Kaplay component object.

```js
function myCustomLogic(speed) {
  return {
    id: "myCustomLogic",
    require: ["pos"],  // Depends on k.pos() being present on the entity
    add() {
      // Runs once when the object is created
    },
    update() {
      // Runs every frame. 'this' refers to the game object.
      // RULE: ALWAYS multiply continuous movement by k.dt()
      this.pos.x += speed * k.dt();
    },
    destroy() {
      // Runs when the object is removed
    },
  };
}
```

**Custom methods and events:**

Components can expose methods and fire custom events via `this.trigger()`:

```js
function healthBar(maxHp) {
  let hp = maxHp;
  return {
    id: "healthBar",
    require: ["pos", "area"],
    takeDamage(amount) {
      hp -= amount;
      if (hp <= 0) this.trigger("death");  // Fire custom event
    },
    getHp() { return hp; },
  };
}

const boss = k.add([k.sprite("dragon"), k.pos(200, 200), k.area(), healthBar(1000)]);
boss.takeDamage(50);           // Call custom method
boss.on("death", () => { /* handle death */ });  // Listen to custom event
```

---

## 9. Math & Utilities

- `k.dt()` — Delta time (seconds since last frame). **CRITICAL: Always multiply continuous movement or timers by this!**
- `k.vec2(x, y)` — Creates a 2D vector.
- `k.rand(min, max)` — Random float between min and max.
- `k.randi(min, max)` — Random integer between min and max.
- `k.center()` — Returns Vec2 of screen center.
- `k.width()` — Canvas width.
- `k.height()` — Canvas height.
- `k.play("soundName")` — Plays an audio file.
- `k.wait(seconds, () => { ... })` — Runs a function after a delay.
- `k.loop(seconds, () => { ... })` — Repeats a function on an interval.

---

## 10. Scenes

Used to manage different game states (menus, levels, game over).

```js
// Define a scene
k.scene("game", () => {
  // Everything inside runs when this scene starts.
  // All objects from the previous scene are automatically destroyed.

  const player = k.add([
    k.sprite("hero"),
    k.pos(100, 100),
    k.area(),
    k.body(),
  ]);

  k.onKeyPress("space", () => {
    player.jump(600);
  });
});

// Start a scene
k.go("game");

// Pass data between scenes
k.scene("gameover", (score) => {
  k.add([
    k.text(`Score: ${score}`, { size: 48 }),
    k.pos(k.center()),
    k.anchor("center"),
  ]);
});

k.go("gameover", 42);
```

---

## 11. Advanced Physics & Effectors

Beyond basic `body()` and `area()`, Kaplay provides **Effectors** for complex physical interactions without custom math.

**Effector components** (pass into `k.add([...])` alongside `k.area()` and `k.body({ isStatic: true })`):

- `k.surfaceEffector({ speed: 100 })` — Conveyor belt: pushes objects along the surface.
- `k.platformEffector({ ignoreSides: [k.UP] })` — One-way platform: objects can jump up through it but stand on top.
- `k.areaEffector({ forceAngle: -90, forceMagnitude: 200 })` — Directional wind/force zone.
- `k.buoyancyEffector({ density: 2 })` — Water/floating simulation.

```js
// Conveyor belt moving objects to the right
k.add([
  k.pos(100, 300), k.rect(200, 20), k.area(),
  k.body({ isStatic: true }),
  k.surfaceEffector({ speed: 100 }),
]);

// One-way platform (jump up through, stand on top)
k.add([
  k.pos(100, 150), k.rect(100, 20), k.area(),
  k.body({ isStatic: true }),
  k.platformEffector({ ignoreSides: [k.UP] }),
]);
```

---

## 12. Particles & Visual Effects

For explosions, smoke, or trails, use the optimized `k.particles()` component instead of spawning individual game objects.

```js
const emitter = k.add([
  k.pos(k.center()),
  k.particles(
    {
      max: 100,              // Max particles alive at once
      speed: [50, 150],      // Min/max speed
      lifeTime: [0.5, 1.5],  // How long particles live
      texture: k.getSprite("spark").data.tex,
      quads: k.getSprite("spark").data.frames,
    },
    {
      direction: -90,        // Emit upwards (degrees)
      spread: 45,            // 45-degree cone
    }
  ),
]);

emitter.emit(20);  // Burst 20 particles (e.g., on explosion)
```

---

## 13. Pathfinding & AI

Kaplay has built-in AI components for enemy navigation and behavior:

- `k.agent({ speed: 100 })` — Pathfinding: calculates routes using the level's navmesh, moves toward a target.
- `k.sentry({ includes: "player" }, { lineOfSight: true })` — Line-of-sight detection: fires events when tagged objects are spotted.
- `k.patrol({ speed: 50 })` — Automated back-and-forth movement between waypoints.

```js
const enemy = k.add([
  k.sprite("goblin"), k.pos(50, 50), k.area(),
  k.agent({ speed: 100 }),
  k.sentry({ includes: "player" }, { lineOfSight: true }),
]);

// When enemy spots the player, chase them
enemy.onObjectsSpotted((objs) => {
  enemy.setTarget(objs[0].pos);  // Agent routes around walls automatically
});
```

---

## 14. Shaders & Rendering Optimization

**Custom shaders** — write GLSL fragment shaders for GPU-level visual effects:

```js
k.loadShader("grayscale", null, `
  vec4 frag(vec2 pos, vec2 uv, vec4 color, sampler2D tex) {
    vec4 tcolor = texture2D(tex, uv);
    float gray = dot(tcolor.rgb, vec3(0.299, 0.587, 0.114));
    return vec4(color.rgb * gray, tcolor.a);
  }
`);

k.add([k.sprite("hero"), k.pos(100, 100), k.shader("grayscale")]);
```

**Optimization techniques:**

- `k.offscreen({ destroy: true })` — Automatically destroy objects when they leave the screen (bullets, particles):

```js
k.add([
  k.sprite("bullet"), k.pos(player.pos),
  k.move(k.RIGHT, 600),
  k.offscreen({ destroy: true }),
]);
```

- **Draw API for static tiles** — If rendering thousands of static tiles, do NOT use `k.add()` for each. Use `k.onDraw()` with raw draw calls:

```js
k.onDraw(() => {
  k.drawSprite({ sprite: "tile", pos: k.vec2(x, y) });
});
```

---

## DEPRECATED KABOOM.JS APIS — DO NOT USE

Kaplay is a fork of Kaboom.js. These old Kaboom APIs **do not exist** in Kaplay:

| ❌ Old Kaboom (BROKEN)       | ✅ Kaplay (CORRECT)          |
|------------------------------|------------------------------|
| `k.origin("center")`        | `k.anchor("center")`         |
| `k.gravity(1600)`           | `k.setGravity(1600)`         |
| `k.layers(["bg", "game"])`  | *(removed — use z() component)* |
| `k.layer("game")`           | `k.z(1)`                     |
| `k.camPos(x, y)`            | `k.setCamPos(x, y)`          |
| `k.camScale(s)`             | `k.setCamScale(s)`           |
| `k.addLevel(...)`           | `k.addLevel(map, opt)`       |

If you use any function from the left column, the game **will crash** with `TypeError: k.xxx is not a function`.

---

## COMMON MISTAKES TO AVOID

1. **DO use ES modules** — `import`/`export` between files. `main.js` passes `k` to other modules as a function argument.
2. **Do NOT create classes** — use `k.add([...components])` composition.
3. **Do NOT use `requestAnimationFrame`** — Kaplay manages the game loop.
4. **Do NOT forget `k.dt()`** — all continuous movement must be frame-rate independent.
5. **Do NOT call `k.add()` outside a scene** unless it's a one-scene game.
6. **Do NOT invent Kaplay methods** — only use functions listed in this reference.
7. **Always include `.js` extension** in import paths (e.g., `import { registerScenes } from "./scenes.js"`).
8. **Do NOT import `kaplay`** — it's a global from the `<script>` tag, only available in `main.js`.
9. **Do NOT use old Kaboom.js APIs** — see the deprecated API table above.
10. **Colors are ALWAYS `k.color(r, g, b)` with three numbers (0-255).** Examples:
    - GOOD: `k.color(0, 255, 0)` — green
    - GOOD: `export const PLAYER_COLOR = [0, 255, 0];` then `k.color(...PLAYER_COLOR)`
    - BAD: `k.color("#00FF00")` — hex strings are NOT supported
    - BAD: `k.color(k.BLACK)` — color constants do NOT exist
    - BAD: `k.rgb(...)` — this function does NOT exist
    - When storing colors in config, use `[r, g, b]` arrays, then spread: `k.color(...MY_COLOR)`
11. **Ensure text is visible** — do not use dark text on a dark background or light text on a light background.
