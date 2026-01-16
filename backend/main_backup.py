import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import vertexai
from vertexai.preview.generative_models import GenerativeModel

app = FastAPI(title="ConYard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Vertex AI
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "conyard")
LOCATION = os.getenv("GCP_LOCATION", "us-central1")

if PROJECT_ID:
    vertexai.init(project=PROJECT_ID, location=LOCATION)

@app.get("/")
async def root():
    return {"message": "ConYard API is running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/generate-animal")
async def generate_animal():
    """Generate a random animal name using Gemini API"""
    try:
        if not PROJECT_ID:
            raise HTTPException(
                status_code=500,
                detail="GCP_PROJECT_ID environment variable not set"
            )
        
        print(f"Using project: {PROJECT_ID}, location: {LOCATION}")
        
        model = GenerativeModel("gemini-2.5-flash")
        
        prompt = "Generate a single random animal name. Reply with only the animal name, nothing else."
        
        print(f"Sending prompt to Gemini...")
        response = model.generate_content(prompt)
        print(f"Response received: {response}")
        
        animal_name = response.text.strip()
        
        return {"animal": animal_name}
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"Failed to generate animal: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)
        raise HTTPException(
            status_code=500,
            detail=error_detail
        )
