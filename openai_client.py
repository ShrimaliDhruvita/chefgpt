import base64
import os
import time
from typing import Optional, Literal

from pydantic import ValidationError

from ..schemas import (
    RecipeFromTextRequest,
    RecipeFromPromptRequest,
    ImageRecipePreferences,
    Recipe,
    Ingredient,
    Step,
    NutritionFacts,
)


# Provider configuration - Using Google Gemini API
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"


def _get_api_key() -> str:
    key = os.getenv(GEMINI_API_KEY_ENV)
    if not key:
        raise RuntimeError(f"Missing {GEMINI_API_KEY_ENV} in environment")
    return key


def _language_instruction(language: Optional[str]) -> str:
    target = (language or "english").strip().lower()
    if not target:
        return "english"
    
    # Map to native script instructions for Indian languages
    script_instructions = {
        "gujarati": "Gujarati script (ગુજરાતી લિપિ) - use actual Gujarati Unicode characters, NOT transliteration",
        "hindi": "Hindi script (देवनागरी) - use actual Devanagari Unicode characters, NOT transliteration",
        "marathi": "Marathi script (देवनागरी) - use actual Devanagari Unicode characters, NOT transliteration",
        "bengali": "Bengali script (বাংলা) - use actual Bengali Unicode characters, NOT transliteration",
        "tamil": "Tamil script (தமிழ்) - use actual Tamil Unicode characters, NOT transliteration",
        "telugu": "Telugu script (తెలుగు) - use actual Telugu Unicode characters, NOT transliteration",
        "kannada": "Kannada script (ಕನ್ನಡ) - use actual Kannada Unicode characters, NOT transliteration",
        "malayalam": "Malayalam script (മലയാളം) - use actual Malayalam Unicode characters, NOT transliteration",
        "punjabi": "Punjabi script (ਪੰਜਾਬੀ) - use actual Gurmukhi Unicode characters, NOT transliteration",
    }
    
    if target in script_instructions:
        return script_instructions[target]
    return target


def _call_with_retries(call_fn, *args, max_attempts: int = 4, initial_delay: float = 1.0, **kwargs):
    """Call `call_fn(*args, **kwargs)` with retries on 429/Quota/Deadline errors.
    Uses exponential backoff between attempts.
    """
    delay = initial_delay
    last_exc = Exception("Call failed after retries")
    for attempt in range(1, max_attempts + 1):
        try:
            return call_fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            msg = str(e).lower()
            # If it's a transient rate/quota/deadline error, retry
            if ('429' in msg) or ('resource exhausted' in msg) or ('quota' in msg) or ('deadline exceeded' in msg) or ('timeout' in msg):
                if attempt == max_attempts:
                    break
                time.sleep(delay)
                delay *= 2
                continue
            # Non-retriable error
            raise
    # If we get here, re-raise last exception
    raise last_exc


def _build_text_prompt(payload: RecipeFromTextRequest) -> str:
    parts = []
    parts.append("You are ChefGPT, a culinary assistant for Indian audiences.\n")
    parts.append("Generate ONE practical recipe using ONLY the provided ingredients if possible.\n")
    parts.append("Respect dietary preferences and aim for balanced nutrition.\n")
    ing = ", ".join(payload.ingredients)
    parts.append(f"Ingredients available: {ing}.\n")
    if payload.cuisine_hint:
        parts.append(f"Cuisine hint: {payload.cuisine_hint}.\n")
    if payload.servings:
        parts.append(f"Target servings: {payload.servings}.\n")
    if payload.cooking_time_limit_minutes:
        parts.append(f"Time limit: {payload.cooking_time_limit_minutes} minutes.\n")
    if payload.dietary:
        prefs = []
        for k, v in payload.dietary.dict(exclude_none=True).items():
            if v:
                prefs.append(k.replace("_", " "))
        if prefs:
            parts.append(f"Dietary: {', '.join(prefs)}.\n")

    language = _language_instruction(payload.language)
    parts.append(f"CRITICAL: Respond entirely in {language}. All text (title, ingredients, steps, tips) must be in the native script, NOT transliteration. Use proper Unicode characters for the language. Keep measurements practical.\n")
    
    # Add variation instruction if this is a regeneration request
    if getattr(payload, 'variation', False):
        import random
        variations = [
            "IMPORTANT: Generate a COMPLETELY DIFFERENT recipe variation. Use different cooking methods, spices, or preparation style. Make it unique from any previous recipe.",
            "IMPORTANT: Create a DISTINCT recipe variation. Try different flavor profiles, cooking techniques, or ingredient combinations. Ensure it's different from previous suggestions.",
            "IMPORTANT: Generate a UNIQUE recipe variation. Experiment with alternative spices, different cooking times, or varied preparation methods. Make it stand out as different.",
            "IMPORTANT: Provide a FRESH recipe variation. Use different spice combinations, alternative cooking methods, or unique presentation. Ensure variety and uniqueness.",
        ]
        parts.append(f"{random.choice(variations)}\n")

    parts.append(
        "Return JSON strictly in this schema: {\n"
        "  'title': str, 'cuisine': str|null, 'servings': int, 'total_time_minutes': int|null,\n"
        "  'ingredients': [{ 'name': str, 'quantity': str|null }],\n"
        "  'steps': [{ 'number': int, 'instruction': str }],\n"
        "  'nutrition': { 'calories': int|null, 'protein_g': float|null, 'carbs_g': float|null, 'fat_g': float|null, 'fiber_g': float|null, 'sodium_mg': float|null }|null,\n"
        "  'tips': [str]|null\n"
        "}\n"
    )
    parts.append("Only output valid JSON with double quotes, no markdown fences.")
    return "".join(parts)


def _extract_and_normalize_json(text: str) -> dict:
    """Extract JSON from model text, repair common issues, and load as dict."""
    import json, re
    candidate = text.strip()
    # If fenced code block, extract
    fence = re.search(r"```(?:json)?\n([\s\S]*?)```", candidate, re.IGNORECASE)
    if fence:
        candidate = fence.group(1).strip()
    # Extract first {...} block if extra prose exists
    brace = re.search(r"\{[\s\S]*\}\s*$", candidate)
    if brace:
        candidate = brace.group(0)
    # Replace single quotes with double quotes (best effort)
    if "'" in candidate and '"' not in candidate:
        candidate = candidate.replace("'", '"')
    # Remove trailing commas before } or ]
    candidate = re.sub(r",\s*(\]|\})", r"\1", candidate)
    return json.loads(candidate)


def _coerce_recipe_dict(data: dict) -> dict:
    """Coerce loosely-structured dict into Recipe-compatible dict."""
    def to_int(value, default):
        try:
            return int(value)
        except Exception:
            return default

    # Build a more user-friendly display title: prefer native title, but
    # include a transliteration/english variant and cuisine when available.
    raw_title = (data.get("title") or data.get("name") or data.get("recipe_name") or "Recipe")
    # Candidate alternate title keys the model might output
    alt_keys = ["title_en", "transliteration", "name_en", "english_title", "recipe_name_en"]
    alt = None
    for k in alt_keys:
        v = data.get(k)
        if v:
            alt = str(v).strip()
            break

    display_title = raw_title
    if alt and alt and alt not in raw_title:
        display_title = f"{raw_title} ({alt})"

    cuisine_val = data.get("cuisine")
    if cuisine_val:
        # Capitalize simple cuisine names for display
        try:
            c = str(cuisine_val).strip()
            if c:
                display_title = f"{display_title} ({c.capitalize()})"
        except Exception:
            pass

    recipe = {
        "title": display_title,
        "cuisine": data.get("cuisine"),
        "servings": to_int(data.get("servings", 2), 2),
        "total_time_minutes": to_int(data.get("total_time_minutes", data.get("time_minutes", 0)), 0) or None,
        "ingredients": [],
        "steps": [],
        "nutrition": data.get("nutrition"),
        "tips": data.get("tips"),
    }
    # Ingredients coercion
    ings = data.get("ingredients") or data.get("ingredient_list") or []
    norm_ings = []
    if isinstance(ings, list):
        for item in ings:
            if isinstance(item, dict):
                name = item.get("name") or item.get("ingredient") or str(item)
                qty = item.get("quantity") or item.get("qty")
            else:
                name = str(item)
                qty = None
            if name:
                norm_ings.append({"name": name, "quantity": qty})
    recipe["ingredients"] = norm_ings or [{"name": "salt", "quantity": "to taste"}]

    # Steps coercion
    steps = data.get("steps") or data.get("instructions") or []
    norm_steps = []
    if isinstance(steps, list):
        for idx, s in enumerate(steps, start=1):
            if isinstance(s, dict):
                instruction = s.get("instruction") or s.get("step") or str(s)
                number = s.get("number") or idx
            else:
                instruction = str(s)
                number = idx
            if instruction:
                norm_steps.append({"number": int(number), "instruction": instruction})
    else:
        # If a long string, split by sentences
        if isinstance(steps, str) and steps.strip():
            parts = [p.strip() for p in steps.split(".") if p.strip()]
            for idx, p in enumerate(parts, start=1):
                norm_steps.append({"number": idx, "instruction": p})
    recipe["steps"] = norm_steps or [{"number": 1, "instruction": "Mix ingredients and cook until done."}]

    return recipe


def _build_image_prompt(preferences: ImageRecipePreferences) -> str:
    parts = []
    parts.append("You are ChefGPT. Identify ingredients visible in the image and propose ONE recipe with a specific descriptive title based on the dish you see.\n")
    if preferences.cuisine_hint:
        parts.append(f"Cuisine hint: {preferences.cuisine_hint}.\n")
    if preferences.servings:
        parts.append(f"Target servings: {preferences.servings}.\n")
    if preferences.cooking_time_limit_minutes:
        parts.append(f"Time limit: {preferences.cooking_time_limit_minutes} minutes.\n")
    if preferences.dietary:
        prefs = []
        for k, v in preferences.dietary.dict(exclude_none=True).items():
            if v:
                prefs.append(k.replace("_", " "))
        if prefs:
            parts.append(f"Dietary: {', '.join(prefs)}.\n")
    language = _language_instruction(preferences.language)
    parts.append(f"CRITICAL: Respond entirely in {language}. All text (title, ingredients, steps, tips) must be in the native script, NOT transliteration. Use proper Unicode characters for the language. Keep instructions concise.\n")
    
    # Add variation instruction if this is a regeneration request
    if getattr(preferences, 'variation', False):
        import random
        variations = [
            "IMPORTANT: Generate a COMPLETELY DIFFERENT recipe variation. Use different cooking methods, spices, or preparation style. Make it unique from any previous recipe.",
            "IMPORTANT: Create a DISTINCT recipe variation. Try different flavor profiles, cooking techniques, or ingredient combinations. Ensure it's different from previous suggestions.",
            "IMPORTANT: Generate a UNIQUE recipe variation. Experiment with alternative spices, different cooking times, or varied preparation methods. Make it stand out as different.",
            "IMPORTANT: Provide a FRESH recipe variation. Use different spice combinations, alternative cooking methods, or unique presentation. Ensure variety and uniqueness.",
        ]
        parts.append(f"{random.choice(variations)}\n")

    parts.append(
        "IMPORTANT: Generate a proper recipe title that describes the actual dish (e.g., 'Chicken Curry', 'Vegetable Biryani', 'Paneer Tikka'). Return strictly JSON with fields: title, ingredients, steps, cuisine, servings, total_time_minutes. Only JSON output."
    )
    return "".join(parts)


async def generate_recipe_from_text(payload: RecipeFromTextRequest) -> Recipe:
    api_key = _get_api_key()
    prompt = _build_text_prompt(payload)

    try:
        import importlib
        try:
            genai = importlib.import_module("google.generativeai")
        except ImportError as ie:
            raise RuntimeError("Missing required package 'google-generativeai'. Install with: pip install google-generativeai") from ie
        genai.configure(api_key=api_key)
        # Use higher temperature for variation requests
        generation_config = {
            "temperature": 0.9 if getattr(payload, 'variation', False) else 0.7,
        }
        model = genai.GenerativeModel('gemini-2.0-flash', generation_config=generation_config)
        # Call with retries to handle transient 429 / quota errors
        response = _call_with_retries(model.generate_content, prompt, request_options={"timeout": 120})
        text = response.text
    except Exception as e:
        print(f"Gemini API error: {str(e)}")
        raise ValueError(f"Recipe generation failed: {str(e)}")

    try:
        data = _extract_and_normalize_json(text)
        data = _coerce_recipe_dict(data)
        return Recipe(**data)
    except Exception as e:
        raise ValueError(f"Failed to parse model output as Recipe JSON: {e}")


async def generate_recipe_from_image(
    image_bytes: bytes,
    filename: Optional[str],
    preferences: ImageRecipePreferences,
) -> Recipe:
    api_key = _get_api_key()
    prompt = _build_image_prompt(preferences)

    try:
        import importlib
        try:
            genai = importlib.import_module("google.generativeai")
        except ImportError as ie:
            raise RuntimeError("Missing required package 'google-generativeai'. Install with: pip install google-generativeai") from ie
        import PIL.Image
        from io import BytesIO

        # Validate and optimize image
        try:
            image = PIL.Image.open(BytesIO(image_bytes))
            if image.mode != 'RGB':
                image = image.convert('RGB')
            max_size = (1500, 1500)
            image.thumbnail(max_size, PIL.Image.Resampling.LANCZOS)
        except Exception as e:
            raise ValueError(f"Failed to process image: {e}")

        genai.configure(api_key=api_key)
        # Use higher temperature for variation requests
        generation_config = {
            "temperature": 0.9 if getattr(preferences, 'variation', False) else 0.7,
        }
        model = genai.GenerativeModel('gemini-2.0-flash', generation_config=generation_config)

        # Send prompt and image to Gemini with increased timeout (120 seconds = 2 minutes)
        # Use the retry helper to handle transient 429/quota/deadline errors
        response = _call_with_retries(model.generate_content, [prompt, image], request_options={"timeout": 120})
        text = response.text

    except Exception as e:
        print(f"Gemini API error: {str(e)}")
        raise ValueError(f"Image analysis failed: {str(e)}")

    try:
        data = _extract_and_normalize_json(text)
        data = _coerce_recipe_dict(data)
        return Recipe(**data)
    except Exception as e:
        raise ValueError(f"Failed to parse image model output as Recipe JSON: {e}")


def _build_prompt_recipe_prompt(payload: RecipeFromPromptRequest) -> str:
    parts = []
    parts.append("You are ChefGPT, a culinary assistant for Indian audiences.\n")
    parts.append("Generate ONE complete recipe based on the user's request.\n")
    parts.append("Include all ingredients, detailed steps, nutrition info, and helpful tips.\n")
    parts.append(f"User request: {payload.prompt}\n")
    if payload.servings:
        parts.append(f"Target servings: {payload.servings}.\n")
    
    language = _language_instruction(payload.language)
    parts.append(f"CRITICAL: Respond entirely in {language}. All text (title, ingredients, steps, tips) must be in the native script, NOT transliteration. Use proper Unicode characters for the language.\n")
    
    if getattr(payload, 'variation', False):
        import random
        variations = [
            "IMPORTANT: Generate a COMPLETELY DIFFERENT recipe variation. Use different cooking methods, spices, or preparation style.",
            "IMPORTANT: Create a DISTINCT recipe variation. Try different flavor profiles, cooking techniques, or ingredient combinations.",
            "IMPORTANT: Generate a UNIQUE recipe variation. Experiment with alternative spices, different cooking times, or varied preparation methods.",
        ]
        parts.append(f"{random.choice(variations)}\n")

    parts.append(
        "Return JSON strictly in this schema: {\n"
        "  'title': str, 'cuisine': str|null, 'servings': int, 'total_time_minutes': int|null,\n"
        "  'ingredients': [{ 'name': str, 'quantity': str|null }],\n"
        "  'steps': [{ 'number': int, 'instruction': str }],\n"
        "  'nutrition': { 'calories': int|null, 'protein_g': float|null, 'carbs_g': float|null, 'fat_g': float|null, 'fiber_g': float|null, 'sodium_mg': float|null }|null,\n"
        "  'tips': [str]|null\n"
        "}\n"
    )
    parts.append("Only output valid JSON with double quotes, no markdown fences.")
    return "".join(parts)


async def generate_recipe_from_prompt(payload: RecipeFromPromptRequest) -> Recipe:
    api_key = _get_api_key()
    prompt = _build_prompt_recipe_prompt(payload)

    try:
        import importlib
        try:
            genai = importlib.import_module("google.generativeai")
        except ImportError as ie:
            raise RuntimeError("Missing required package 'google-generativeai'. Install with: pip install google-generativeai") from ie
        genai.configure(api_key=api_key)
        generation_config = {
            "temperature": 0.9 if getattr(payload, 'variation', False) else 0.7,
        }
        model = genai.GenerativeModel('gemini-2.0-flash', generation_config=generation_config)
        response = _call_with_retries(model.generate_content, prompt, request_options={"timeout": 120})
        text = response.text
    except Exception as e:
        print(f"Gemini API error: {str(e)}")
        raise ValueError(f"Recipe generation failed: {str(e)}")

    try:
        data = _extract_and_normalize_json(text)
        data = _coerce_recipe_dict(data)
        return Recipe(**data)
    except Exception as e:
        raise ValueError(f"Failed to parse model output as Recipe JSON: {e}")


