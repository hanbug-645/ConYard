# ConYard Setup Guide

## Prerequisites
- Node.js 18+ and npm
- Python 3.11+
- A Gemini API key **or** a GCP project with Vertex AI enabled (see Auth below)

## Local Development Setup

The current implementation is a frontend/backend scaffold with a Gemini connectivity demo. The planned game-generation flow also includes an `engine/` folder that contains documentation and template assets for browser-playable games.

### 1. Backend Setup

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and add your GCP_PROJECT_ID

# Run the server
uvicorn main:app --reload
```

Backend will be available at http://localhost:8000

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Configure environment variables
cp .env.local.example .env.local
# Edit .env.local if needed (default points to localhost:8000)

# Run the development server
npm run dev
```

Frontend will be available at http://localhost:3000

## Authentication

Two modes are supported. Set one in `backend/.env`:

### Option A — Google AI API key (simplest for local dev)
```
GOOGLE_API_KEY=your-key-here
```
No GCP project or `gcloud` login needed.

### Option B — Vertex AI (production / GCP project)
```
GCP_PROJECT_ID=your-project-id
GCP_LOCATION=us-central1
```
Then authenticate locally:
```bash
gcloud auth application-default login
```

## Testing the Application

1. Start the backend server (port 8000)
2. Start the frontend server (port 3000)
3. Open http://localhost:3000 in your browser
4. Describe a Snake, Flappy Bird, or Pac-Man-style game in the chat
5. The frontend calls `/game-turn`, which plans, generates, validates, and previews the game

## Engine Template Setup

The `engine/` folder does not require a separate server process.

For the MVP design:

1. `engine/template_manager.py` maps a user requirement to a template manifest.
2. `engine/templates/` contains the Snake, Flappy Bird, and Pac-Man templates.
3. Each template exports one base class that generated `game.js` files extend.
4. Template-owned supporting files live in the template's `dep/` folder.
5. The backend packages generated `game.js`, its base class, entry, and dependencies.

No additional local setup is required until the backend and frontend implement this template-loading flow.

## Cloud Run Deployment

See the PRD.md for detailed deployment instructions using GitHub integration with Cloud Run.

### Quick Deploy Steps:

1. Push code to GitHub repository
2. In Google Cloud Console, create two Cloud Run services:
   - Backend: Source location `/backend/Dockerfile`
   - Frontend: Source location `/frontend/Dockerfile`
3. Set environment variables:
   - Backend: `GCP_PROJECT_ID`, `GCP_LOCATION`
   - Frontend: `NEXT_PUBLIC_API_URL` (pointing to backend service URL)
4. Configure Cloud Build triggers to watch respective folders

When template files become part of runtime generation, include `engine/**` in the backend deployment trigger so template updates redeploy the service that reads them.

## Environment Variables

### Backend (`backend/.env`)
| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | Option A only | Google AI API key |
| `GCP_PROJECT_ID` | Option B only | GCP project ID |
| `GCP_LOCATION` | Option B only | GCP region (default: `us-central1`) |

### Frontend (`frontend/.env.local`)
| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend API URL |
