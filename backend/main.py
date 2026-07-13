import json
import os
import re
import sys
import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()  # loads backend/.env if present

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import vertexai
from vertexai.preview.generative_models import GenerativeModel

from llm import get_llm
from llm.prompts import edit_prompt, generation_prompt, planning_prompt

# Make engine/ importable when running from backend/ or repo root
sys.path.insert(0, str(Path(__file__).parent.parent))
from engine.template_manager import TemplateManager, Template

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

# Initialize Vertex AI only when not using API key mode
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "conyard")
LOCATION   = os.getenv("GCP_LOCATION", "us-central1")
_using_api_key = bool(os.getenv("GOOGLE_API_KEY"))

if _using_api_key:
    logger.info("Starting ConYard API  auth=GOOGLE_API_KEY")
else:
    logger.info(f"Starting ConYard API  auth=VertexAI  project={PROJECT_ID}  location={LOCATION}")
    if PROJECT_ID:
        try:
            vertexai.init(project=PROJECT_ID, location=LOCATION)
            logger.info("Vertex AI initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Vertex AI: {str(e)}", exc_info=True)

@app.get("/")
async def root():
    return {"message": "ConYard API is running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}


# ---------------------------------------------------------------------------
# Pydantic models for /game-turn
# ---------------------------------------------------------------------------

class Message(BaseModel):
    role: str
    text: str

class GameTurnState(BaseModel):
    template_id: Optional[str] = None
    phase: str = "new"
    summary: str = ""
    pending_question: Optional[str] = None
    generated_code: Optional[str] = None
    recent_messages: list[Message] = []

class GameTurnRequest(BaseModel):
    message: str
    state: GameTurnState

class GameTurnResponse(BaseModel):
    type: str
    message: str
    html: Optional[str] = None
    generated_code: Optional[str] = None
    state: GameTurnState


# ---------------------------------------------------------------------------
# Template manager (lazy singleton)
# ---------------------------------------------------------------------------

_tm: Optional[TemplateManager] = None

def get_tm() -> TemplateManager:
    global _tm
    if _tm is None:
        _tm = TemplateManager()
    return _tm


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

def _build_template_registry(tm: TemplateManager) -> list[dict]:
    """Compact template list shown to the planning LLM."""
    result = []
    for t in tm._templates:
        base_src = (t.template_dir / "base.js").read_text(encoding="utf-8")
        hook_names = re.findall(r'name:\s*"([^"]+)"', base_src)
        result.append({
            "id": t.template_id,
            "name": t.manifest.get("name", t.template_id),
            "description": t.manifest.get("description", ""),
            "routing_keywords": t.manifest.get("routing_keywords", []),
            "hook_names": hook_names,
        })
    return result


def _build_examples_block(template: Template) -> str:
    """Read up to 4 example files into a single annotated string."""
    block = ""
    for ex in sorted((template.template_dir / "example").glob("game_*.js"))[:4]:
        block += f"\n// === {ex.name} ===\n{ex.read_text(encoding='utf-8')}\n"
    return block


def validate_game_js(game_js: str, template: Template) -> Optional[str]:
    """Returns an error string on failure, None on success."""
    base_class = template.manifest.get("base_class", "SnakeGame")
    if "```" in game_js:
        return "code contains Markdown fences"
    if 'from "./base.js"' not in game_js and "from './base.js'" not in game_js:
        return "missing import from base.js"
    if f"extends {base_class}" not in game_js:
        return f"does not extend {base_class}"
    if "mount(" not in game_js:
        return "missing mount() call"
    if "dep/" in game_js:
        return "imports from dep/ directly"
    return None


# ---------------------------------------------------------------------------
# HTML bundler — flattens engine.js + base.js + optional game.js into one
# self-contained HTML document safe for iframe srcDoc rendering.
# ---------------------------------------------------------------------------

def build_html(template: Template, game_js: Optional[str] = None) -> str:
    d = template.template_dir
    engine_src = (d / "dep" / "engine.js").read_text(encoding="utf-8")
    base_src   = (d / "base.js").read_text(encoding="utf-8")
    styles_src = (d / "dep" / "styles.css").read_text(encoding="utf-8")

    # engine.js: strip `export` from the class declaration
    engine_src = re.sub(r'\bexport\s+class\s+', 'class ', engine_src)

    # base.js transformations
    # 1. Remove import lines
    base_src = re.sub(r'^import\s+.+?;\s*$', '', base_src, flags=re.MULTILINE)
    # 2. Remove `export { ... };` re-export lines
    base_src = re.sub(r'^export\s+\{[^}]*\};\s*$', '', base_src, flags=re.MULTILINE)
    # 3. Remove the HOOKS array export (multi-line)
    base_src = re.sub(r'export const HOOKS = \[.*?\];', '', base_src, flags=re.DOTALL)
    # 4. Demote `export function` → `function`
    base_src = re.sub(r'\bexport\s+function\s+', 'function ', base_src)
    # 5. Remove the CSS link injection inside mount() — styles are already inlined
    base_src = re.sub(
        r'\s*if\s*\(!document\.querySelector\(\'link\[data-snake-styles\]\'\)\)\s*\{[^}]*\}',
        '',
        base_src,
        flags=re.DOTALL,
    )

    # game_js: strip its import line (base is already in scope)
    if game_js:
        game_js = re.sub(r'^import\s+.+?;\s*$', '', game_js, flags=re.MULTILINE)
        custom_block = game_js
    else:
        custom_block = ""  # base.js queueMicrotask auto-mounts the default game

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{template.manifest.get('name', 'Game')}</title>
  <style>
{styles_src}
  </style>
</head>
<body>
<script type="module">
{engine_src}

{base_src}
{custom_block}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# POST /game-turn  — stateless turn handler (Steps 3 + 4: real LLM)
# ---------------------------------------------------------------------------


@app.post("/game-turn", response_model=GameTurnResponse)
async def game_turn(req: GameTurnRequest):
    msg   = req.message.strip()
    state = req.state

    try:
        tm = get_tm()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Template manager error: {exc}")

    try:
        registry    = _build_template_registry(tm)
        new_recent  = (state.recent_messages + [Message(role="user", text=msg)])[-6:]
        recent_plain = [{"role": m.role, "text": m.text} for m in state.recent_messages]
        llm         = get_llm()

        # Step B: planning LLM decides action
        plan_prompt = planning_prompt(
            message=msg,
            phase=state.phase,
            has_game=bool(state.generated_code),
            summary=state.summary,
            pending_question=state.pending_question,
            recent_messages=recent_plain,
            registry=registry,
        )
        try:
            decision = llm.call_json(plan_prompt)
        except Exception as exc:
            logger.warning("Planning LLM failed, falling back to generate: %s", exc)
            decision = {
                "action": "generate",
                "template_id": registry[0]["id"] if registry else None,
                "question": None,
                "summary": state.summary or f"User requested: {msg}",
            }

        action      = decision.get("action", "generate")
        tmpl_id     = decision.get("template_id")
        question    = decision.get("question")
        new_summary = decision.get("summary", state.summary)

        logger.info("Planning → action=%s  template=%s", action, tmpl_id)

        # Step C: ask clarification
        if action == "ask" and question:
            template = tm.select(tmpl_id or msg)
            return GameTurnResponse(
                type="question",
                message=question,
                state=GameTurnState(
                    template_id=template.template_id,
                    phase="awaiting_clarification",
                    summary=new_summary,
                    pending_question=question,
                    generated_code=state.generated_code,
                    recent_messages=new_recent,
                ),
            )

        # Unsupported
        if action == "unsupported":
            return GameTurnResponse(
                type="message",
                message=new_summary or "I don't have a suitable template for that yet.",
                state=GameTurnState(
                    template_id=state.template_id,
                    phase=state.phase,
                    summary=new_summary,
                    pending_question=None,
                    generated_code=state.generated_code,
                    recent_messages=new_recent,
                ),
            )

        # Steps D / E: generate or edit
        template   = tm.select(tmpl_id or msg)
        base_src   = (template.template_dir / "base.js").read_text(encoding="utf-8")
        base_class = template.manifest.get("base_class", "GameBase")

        if action == "edit" and state.generated_code:
            raw_js = llm.call(
                edit_prompt(
                    message=msg,
                    recent_messages=recent_plain,
                    base_class=base_class,
                    base_src=base_src,
                    generated_code=state.generated_code,
                ),
                temperature=0.3,
            )
        else:
            raw_js = llm.call(
                generation_prompt(
                    message=msg,
                    summary=new_summary,
                    recent_messages=recent_plain,
                    template_name=template.manifest.get("name", "game"),
                    base_class=base_class,
                    base_src=base_src,
                    examples_block=_build_examples_block(template),
                ),
                temperature=0.4,
            )

        # Strip Markdown fences if the LLM added them anyway
        game_js = re.sub(r'^```(?:javascript|js)?\s*\n?', '', raw_js, flags=re.MULTILINE)
        game_js = re.sub(r'\n?```\s*$', '', game_js, flags=re.MULTILINE).strip()

        # Step F: validate
        err = validate_game_js(game_js, template)
        if err:
            logger.warning(f"Validation failed ({err}).\nFirst 500 chars:\n{game_js[:500]}")
            return GameTurnResponse(
                type="message",
                message=f"I had trouble generating valid code ({err}). Please try rephrasing.",
                state=GameTurnState(
                    template_id=template.template_id,
                    phase=state.phase,
                    summary=new_summary,
                    pending_question=None,
                    generated_code=state.generated_code,
                    recent_messages=new_recent,
                ),
            )

        # Step G: build HTML
        html = build_html(template, game_js)
        verb = "Updated" if action == "edit" else "Here's"
        return GameTurnResponse(
            type="game",
            message=f"{verb} your {template.manifest['name']} game!",
            html=html,
            generated_code=game_js,
            state=GameTurnState(
                template_id=template.template_id,
                phase="ready",
                summary=new_summary,
                pending_question=None,
                generated_code=game_js,
                recent_messages=new_recent,
            ),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("game_turn error")
        raise HTTPException(status_code=500, detail=str(exc))


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
