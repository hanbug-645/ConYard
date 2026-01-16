import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import vertexai
from vertexai.preview.generative_models import GenerativeModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

logger.info(f"Starting ConYard API with PROJECT_ID={PROJECT_ID}, LOCATION={LOCATION}")

if PROJECT_ID:
    try:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        logger.info(f"Vertex AI initialized successfully for project {PROJECT_ID}")
    except Exception as e:
        logger.error(f"Failed to initialize Vertex AI: {str(e)}", exc_info=True)

@app.get("/")
async def root():
    return {"message": "ConYard API is running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/generate-animal")
async def generate_animal():
    """Generate a random animal name using Gemini API"""
    logger.info("=== Generate Animal Request Started ===")
    
    try:
        # Check project ID
        if not PROJECT_ID:
            logger.error("GCP_PROJECT_ID not set")
            raise HTTPException(
                status_code=500,
                detail="GCP_PROJECT_ID environment variable not set"
            )
        
        logger.info(f"Using project: {PROJECT_ID}, location: {LOCATION}")
        
        # Initialize model
        logger.info("Initializing GenerativeModel with gemini-2.5-flash")
        try:
            model = GenerativeModel("gemini-2.5-flash")
            logger.info("Model initialized successfully")
        except Exception as model_error:
            logger.error(f"Failed to initialize model: {str(model_error)}", exc_info=True)
            raise
        
        # Prepare prompt
        prompt = "Generate a single random animal name. Reply with only the animal name, nothing else."
        logger.info(f"Prompt prepared: {prompt}")
        
        # Call Gemini API
        logger.info("Calling Gemini API...")
        try:
            response = model.generate_content(prompt)
            logger.info(f"API call successful. Response type: {type(response)}")
            logger.info(f"Response object: {response}")
        except Exception as api_error:
            logger.error(f"Gemini API call failed: {str(api_error)}", exc_info=True)
            raise
        
        # Extract text
        try:
            animal_name = response.text.strip()
            logger.info(f"Successfully extracted animal name: {animal_name}")
        except Exception as extract_error:
            logger.error(f"Failed to extract text from response: {str(extract_error)}", exc_info=True)
            raise
        
        logger.info(f"=== Generate Animal Request Completed: {animal_name} ===")
        return {"animal": animal_name}
    
    except HTTPException as http_exc:
        logger.error(f"HTTP Exception: {http_exc.detail}")
        raise
    except Exception as e:
        import traceback
        error_detail = f"Failed to generate animal: {str(e)}"
        error_trace = traceback.format_exc()
        logger.error(f"Unexpected error: {error_detail}")
        logger.error(f"Traceback: {error_trace}")
        raise HTTPException(
            status_code=500,
            detail=error_detail
        )
