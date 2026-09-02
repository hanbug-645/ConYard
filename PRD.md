# Product Requirement Document (PRD): ConYard IDE Interface

## Document Information
- **Version**: 1.0 (Draft)
- **Status**: In Development
- **Scope**: Web-Based Editor Interface (Desktop Only)
- **Codename**: ConYard
- **Date**: January 16, 2026
- **Author**: Hanbug

## 1. Executive Summary
ConYard is an AI-native game development platform that democratizes game creation. The core interface mimics a "pair programming" session where the user acts as the Creative Director and the AI acts as the Lead Engineer.

The objective of this PRD is to define the Web IDE, a split-screen "Canvas" environment where natural language prompts are instantly transmuted into playable TypeScript games (Phaser/Babylon.js).

For the MVP, ConYard will use a template-first engine rather than generating every game from scratch. User prompts are mapped to a supported game template, customized through explicit template interfaces, bundled with any template dependencies, and sent to the browser for immediate play. The first supported template is Snake.

## 2. User Personas
### The Visionary (Primary):
Has a game idea but zero coding skills. Needs the AI to handle 100% of the implementation.

### The Tweaker (Secondary):
Knows basic code. Wants the AI to build the boilerplate, but wants the ability to inspect and manually adjust values (jump height, speed) in the code.

## 3. Functional Requirements

### 3.1 The "Workbench" Layout
The interface must be a Single Page Application (SPA) utilizing a split-pane architecture.

#### FR-1.1 Resizable Split:
- Use a vertical split layout.
- Left Panel (40% default): "Command Center" (Chat & Context).
- Right Panel (60% default): "Viewport" (Game Preview & Code).
- Drag Handle: Users must be able to drag the divider to resize panels.

#### FR-1.2 Theme:
- Default to Dark Mode (high contrast for code readability).
- Aesthetics should feel "industrial/technical" (nod to the Factory theme).

### 3.2 The Command Center (Left Panel)
This is where the user inputs intent and receives feedback.

#### FR-2.1 Context-Aware Chat:
- Standard chat interface (Input at bottom, history flows up).
- Streaming Responses: AI text must stream token-by-token.
- Markdown Support: Render headers, lists, and inline code snippets cleanly.

#### FR-2.2 "Apply" Logic:
- Unlike standard ChatGPT, code blocks are not just displayed in chat. They are automatically "piped" to the Right Panel.
- Status Indicators: Show "Thinking...", "Coding...", "Compiling..." states clearly.
- Template Selection: The backend must pass each game request to `engine/template_manager.py` and select a template manifest before generating browser files.

#### FR-2.3 History & Rollback:
- Users can scroll up to see previous prompts.
- "Revert to Here": A button on previous messages to reset the code state to that specific point in time (Time Machine).

### 3.3 The Viewport (Right Panel)
This is the "Artifact" area where the game comes to life. It has two modes: Preview and Code.

#### FR-3.1 Mode Switcher:
- Tabs at the top: [ Play ] | [ Code ] | [ Logs ].

#### FR-3.2 The Preview Tab (Default):
- Sandboxed Renderer: Renders the active App.tsx / Game.ts file.
- Auto-Reload: When code changes, the game auto-refreshes (Hot Module Replacement).
- Focus Management: Clicking into the game canvas must capture keyboard inputs (WASD) so they don't trigger chat shortcuts.

#### FR-3.3 The Code Tab:
- Read-Only View (MVP): Syntax-highlighted view of the generated code.
- Manual Edit (Post-MVP): Allow users to manually type fixes. For v1.0, this is Read-Only to prevent state desync with the AI.

#### FR-3.4 The Console Tab:
- Capture console.log and console.error from the sandboxed game and display them here.
- Critical: If the game crashes (Red Screen of Death), automatically switch to this tab to show the error trace.

## 4. Technical Specifications

### 4.1 Architecture
- **Framework**: Next.js 14+ (App Router).
- **State Management**: React `useState` / `useRef` (local component state for MVP; Zustand available for later phases).
- **Game Renderer**: `<iframe srcDoc={html} sandbox="allow-scripts" />` — the backend assembles a single self-contained HTML document (engine + base class + generated game inlined) and returns it directly. No Sandpack, no Blob URLs, no server-side preview storage.
- **LLM**: Google Gemini (`gemini-3.8-flash`) via the `google-genai` SDK. Supports both API-key auth (`GOOGLE_API_KEY`) and Vertex AI auth (`GCP_PROJECT_ID` / `GCP_LOCATION`). Conversation continuity uses Gemini's Interactions API (`previous_interaction_id`), so the frontend does not need to echo message history.
- **Template Engine**: File-based library under `engine/templates/`. The manager selects a manifest, a code agent writes one `game.js` subclass file, and the backend inlines the base class and dependencies into a single HTML document.

### 4.2 Game Template Engine

#### MVP Template Scope:
- The MVP supports Snake, Flappy Bird, and Pac-Man templates.
- Requests are mapped by keyword and LLM planning to the closest installed template.
- Requests outside the supported set trigger an `unsupported` planning action; the backend returns a friendly message suggesting the closest available template.

#### Engine Folder Structure:
```text
/ConYard
  ├── /engine
  │   ├── template_manager.py
  │   ├── template.md
  │   └── /templates
  │       ├── /snake
  │       │   ├── manifest.json   (name, description, base_class, routing_keywords)
  │       │   ├── base.js         (stable base class + HOOKS contract)
  │       │   ├── /example        (few-shot reference game.js files)
  │       │   └── /dep            (engine.js, styles.css)
  │       ├── /flappybird
  │       └── /pacman
```

#### Template Contract:
- Each template folder contains one stable base class file.
- The base class contains the complete game engine and explicit extension interfaces.
- The code agent creates one `game.js` subclass for each user request.
- Template-specific dependency files live in the template's `dep/` folder.
- Generated user games inherit from the template instead of being invented from scratch.

#### Browser Bundle Contract:
When a user request is processed, the backend should produce a file bundle containing:

- The customized game file derived from the selected template.
- Every required dependency file from the selected template's `dep/` folder.
- Metadata needed by the frontend sandbox to identify the entry file.

The frontend should load this bundle into the browser sandbox and render it in the Play tab.

### 4.3 Error Handling (The "Self-Healing" Loop)
- **Validation**: Backend validates the generated `game.js` before returning it (checks imports, class extension, `mount()` call). On failure, one automated repair call is attempted before returning a friendly error to the user.
- **AI Feedback** _(post-MVP)_: A "Fix It" button that feeds a runtime error trace back into the conversation as a new prompt.

## 5. UI/UX Wireframe Description

### Header (Nav):
[ ConYard Logo ] [ Project Name: "Space Invaders" ] [ Export Button ]

### Body (Split View):
#### Left Panel (Command)
- Chat History:
  - User: "Make the ship blue."
  - AI: "Updating sprite tint..."
- Input Area:
  [ Type instruction... ]

#### Right Panel (Viewport)
- Tabs: [▶ Play] [Current.ts] [Console]
- Canvas Area:
  [Code updated]
  [ 800x600 Game Canvas ]
  (Rendering Phaser/Babylon Scene)
- Status Bar:
  Ready | 60 FPS | TypeScript

## 6. Success Metrics (v1.0)
- **Latency**: Time from "Enter" to "Game Updating" < 3 seconds.
- **Stability**: Session lasts > 10 minutes without browser crash (memory leak check).
- **Completion**: User can complete the loop "Prompt -> Game -> Play" without leaving the interface.

## 7. Future Considerations (Out of Scope for v1.0)
- Asset Library: Global shared assets (as discussed previously).
- Multiplayer Editing: Google Docs style collaboration.
- Mobile Support: Responsive layout for phones.

## 8. Deployment Architecture

### 8.1 Repository Structure
The ConYard project will be organized as a monorepo with the following structure:
```
/ConYard
  ├── /frontend      (Next.js code, package.json, Dockerfile)
  ├── /backend       (FastAPI code, requirements.txt, Dockerfile)
  ├── /engine        (template router and game templates)
  └── README.md
```

### 8.2 Cloud Run Deployment Strategy
Two separate Cloud Run services will be created, both connected to the same GitHub repository:

#### Service A: Backend (FastAPI)
- **Build Configuration**: Source location `/backend/Dockerfile`
- **Ingress**: Allow unauthenticated invocations
- **Trigger**: Watches for changes in `/backend/**` and, once template loading is implemented, `/engine/**`

#### Service B: Frontend (Next.js)
- **Build Configuration**: Source location `/frontend/Dockerfile`
- **Environment Variables**: `NEXT_PUBLIC_API_URL` pointing to Backend Service URL
- **Trigger**: Watches for changes in `/frontend/**`

### 8.3 Automated Deployment Pipeline
- **Continuous Deployment**: Direct GitHub repository linking to Cloud Run
- **Build Triggers**: Cloud Build automatically created for each service
- **Selective Deployment**: Only the modified service (frontend/backend) redeploys on commit
- **Workflow**: Git push → Automated build → Deployment within ~2 minutes

### 8.4 Monorepo Filtering
- **Backend Trigger**: Included files filter set to `backend/**`
- **Frontend Trigger**: Included files filter set to `frontend/**`
- **Engine Trigger**: Include `engine/**` with the backend trigger when templates are read by the backend at build or runtime
- **Purpose**: Prevents unnecessary deployments when non-code files change

---

## Change Log
| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2026-01-16 | 1.0 | Initial PRD creation | Hanbug |
| 2026-06-30 | 1.1 | Added template-first engine design and Snake MVP scope | Hanbug |
| 2026-09-02 | 1.2 | Updated tech stack: iframe renderer (not Sandpack), vanilla JS engine (not Phaser/Babylon), three templates (Snake/Flappy/Pac-Man), Gemini Interactions API for conversation state | Hanbug |
