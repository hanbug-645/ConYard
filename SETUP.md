# ConYard Setup Guide

## Prerequisites
- Node.js 18+ and npm
- Python 3.11+
- Google Cloud Platform account with Vertex AI API enabled
- GCP credentials configured

## Local Development Setup

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

## GCP Authentication

For local development, authenticate with GCP:

```bash
gcloud auth application-default login
```

## Testing the Application

1. Start the backend server (port 8000)
2. Start the frontend server (port 3000)
3. Open http://localhost:3000 in your browser
4. Click "Generate Random Animal" button
5. The frontend will call the backend, which calls Gemini API to generate an animal name

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

## Environment Variables

### Backend (.env)
- `GCP_PROJECT_ID`: Your Google Cloud Project ID
- `GCP_LOCATION`: GCP region (default: us-central1)

### Frontend (.env.local)
- `NEXT_PUBLIC_API_URL`: Backend API URL (default: http://localhost:8000)
