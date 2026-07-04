# ConYard

AI-native game development platform that democratizes game creation through natural language prompts.

## Repository Structure
```
/ConYard
  ├── /frontend      (Next.js app, browser preview, package.json, Dockerfile)
  ├── /backend       (FastAPI API, AI/template orchestration, Dockerfile)
  ├── /engine        (game template selection and reusable game templates)
  │   ├── template.md
  │   └── /snake
  │       └── /dep
  └── README.md
```

## Architecture
- **Frontend**: Next.js 14+ with split-screen IDE interface and browser-based game preview
- **Backend**: FastAPI for AI service integration and template orchestration
- **Engine**: File-based game template library. The MVP maps user requests to a supported game template, currently Snake.
- **Deployment**: Google Cloud Run with continuous deployment from GitHub

## Template Engine Concept
ConYard uses a template-first generation flow for predictable browser-playable games.

1. A user sends a natural language game request.
2. The backend uses `engine/template_manager.py` and template manifests to choose a supported template.
3. For the MVP, only the Snake template is supported.
4. The selected template provides a stable base class with explicit extension interfaces.
5. Optional supporting dependency files live under that template's `dep/` folder.
6. A code agent writes one subclass file; the backend packages it with the base class and dependencies.
7. The frontend loads the files into the browser sandbox so the user can play immediately.

## Development
See individual folder READMEs for setup instructions.
