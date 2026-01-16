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
- **State Management**: Zustand (for global Client State) + React Context.
- **Sandboxing**: @codesandbox/sandpack-react. This is non-negotiable for handling complex dependency trees (Phaser, Babylon) entirely in the browser.

### 4.2 The "Streaming Parser"
To achieve the "Canvas" feel, the frontend must parse the LLM stream in real-time.

#### Regex Logic:
- Detect ```typescript opening tag.
- Capture content into a hidden buffer.
- On ``` closing tag (or stream end), trigger a Sandpack File Update.
- Debounce: Update the Sandpack instance max once every 1000ms to prevent render thrashing while the AI is typing.

### 4.3 Error Handling (The "Self-Healing" Loop)
- **Runtime Errors**: If the Sandpack frame throws an error, catch it via ErrorBoundary.
- **AI Feedback**: Add a "Fix It" button next to the error log. Clicking it feeds the error stack trace back into the Chat Context as a new system prompt: "The previous code crashed with: [Error]. Fix it."

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
  └── README.md
```

### 8.2 Cloud Run Deployment Strategy
Two separate Cloud Run services will be created, both connected to the same GitHub repository:

#### Service A: Backend (FastAPI)
- **Build Configuration**: Source location `/backend/Dockerfile`
- **Ingress**: Allow unauthenticated invocations
- **Trigger**: Watches for changes in `/backend/**`

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
- **Purpose**: Prevents unnecessary deployments when non-code files change

---

## Change Log
| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2026-01-16 | 1.0 | Initial PRD creation | Hanbug |
