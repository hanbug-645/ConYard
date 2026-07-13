"""Prompt builders for each LLM call in the game-turn pipeline.

All functions accept plain Python types (strings, dicts, lists) — no
Pydantic models — so this module stays independent of the FastAPI layer
and is easy to unit-test or update without touching the route code.
"""

import json


def planning_prompt(
    *,
    message: str,
    phase: str,
    has_game: bool,
    summary: str,
    pending_question: str | None,
    recent_messages: list[dict],
    registry: list[dict],
) -> str:
    """Build the planning prompt that returns a routing decision as JSON."""
    recent = "\n".join(f"  {m['role']}: {m['text']}" for m in recent_messages)

    return f"""You are a game creation assistant. Decide the next action.

Return ONLY valid JSON with this exact structure:
{{
  "action": "ask" | "generate" | "edit" | "unsupported",
  "template_id": "<id from available templates, or null>",
  "question": "<one short question \u2014 only when action is ask>",
  "summary": "<concise one-sentence summary of what the user wants>"
}}

Rules:
- User has an existing game (has_game=true) and gives feedback \u2192 action: edit
- No game, request is clear \u2192 action: generate
- No game, a critical template-specific detail is unknown \u2192 action: ask with ONE question
- No template fits the request \u2192 action: unsupported (explain in summary)
- Do NOT ask about things with sensible defaults (colors, speed, etc.)
- Ask at most one question per turn

Available templates:
{json.dumps(registry, indent=2)}

State:
  phase: {phase}
  has_game: {has_game}
  summary_so_far: {summary or 'none'}
  pending_question: {pending_question or 'none'}

Recent conversation:
{recent or '  (none)'}

User\u2019s latest message: {message}

Respond with ONLY the JSON object. No explanation, no markdown, no extra text."""


def generation_prompt(
    *,
    message: str,
    summary: str,
    recent_messages: list[dict],
    template_name: str,
    base_class: str,
    base_src: str,
    examples_block: str,
) -> str:
    """Build the generation prompt for a brand-new game.js subclass."""
    recent = "\n".join(f"  {m['role']}: {m['text']}" for m in recent_messages)

    return f"""You are a JavaScript game developer. Generate a customized {template_name} game subclass.

STRICT CONTRACT \u2014 follow exactly or the code will be rejected:
1. First line: import {{ {base_class}, mount }} from "./base.js";
2. ONE class extending {base_class} with a descriptive name
3. Override only the hooks needed; do not redefine defaults
4. Last line: mount(YourClassName);
5. No Markdown fences (no backticks anywhere)
6. No imports except the one above; no dep/ imports

AVAILABLE HOOKS (all overridable methods):
{base_src}

EXAMPLE GAMES (match this style exactly):
{examples_block}

CONTEXT:
  Summary: {summary or 'New request'}
  Recent:
{recent or '  (none)'}

USER REQUEST: {message}

Output JavaScript only:"""


def edit_prompt(
    *,
    message: str,
    recent_messages: list[dict],
    base_class: str,
    base_src: str,
    generated_code: str,
) -> str:
    """Build the edit prompt to rewrite an existing game.js based on feedback."""
    recent = "\n".join(f"  {m['role']}: {m['text']}" for m in recent_messages)

    return f"""You are a JavaScript game developer. Edit an existing game subclass.

STRICT CONTRACT:
1. Keep: import {{ {base_class}, mount }} from "./base.js";
2. Return the COMPLETE updated file, not just the changed parts
3. No Markdown fences, no extra imports, no dep/ imports

AVAILABLE HOOKS (for reference):
{base_src}

CURRENT GAME:
{generated_code}

RECENT CONVERSATION:
{recent or '  (none)'}

USER FEEDBACK: {message}

Output complete updated JavaScript only:"""
