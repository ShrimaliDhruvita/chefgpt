from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Response, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from typing import Optional

from .schemas import (
    HealthResponse,
    RecipeFromTextRequest,
    RecipeFromPromptRequest,
    RecipeResponse,
    ImageRecipePreferences,
    UserSignup,
    UserLogin,
    UserResponse,
    SaveRecipeRequest,
    SavedRecipeResponse,
    SavedRecipesListResponse,
)
from .services.openai_client import (
    generate_recipe_from_text,
    generate_recipe_from_image,
    generate_recipe_from_prompt,
)
from .auth import get_current_user, require_auth, login_user, logout_user
from .database import db

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    # dotenv is optional; ignore if not installed
    pass


app = FastAPI(title="ChefGPT", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/", response_class=HTMLResponse)
def index(session_token: Optional[str] = Cookie(None)) -> HTMLResponse:
    user = get_current_user(session_token)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    try:
        with open("app/static/index.html", "r", encoding="utf-8") as f:
            content = f.read()
            # Add user info to the page
            content = content.replace(
                '<div id="health" class="badge badge-warn">Checking...</div>',
                f'<div class="user-info">Welcome, {user["name"]}! <a href="/saved-recipes">📋 My Recipes</a> | <a href="/logout">Logout</a></div><div id="health" class="badge badge-warn">Checking...</div>'
            )
            return HTMLResponse(content=content)
    except FileNotFoundError:
        return HTMLResponse("<h1>ChefGPT</h1><p>Static UI not found. Ensure app/static/index.html exists.</p>")


@app.get("/saved-recipes", response_class=HTMLResponse)
def saved_recipes_page(session_token: Optional[str] = Cookie(None)) -> HTMLResponse:
    user = get_current_user(session_token)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    try:
        with open("app/static/saved-recipes.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>Saved Recipes</h1><p>Saved recipes page not found.</p>")


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>ChefGPT - Login</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 400px; margin: 100px auto; padding: 20px; }
            .form-group { margin-bottom: 15px; }
            label { display: block; margin-bottom: 5px; }
            input { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
            button { width: 100%; padding: 10px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background: #0056b3; }
            .error { color: red; margin-top: 10px; }
            .link { text-align: center; margin-top: 15px; }
        </style>
    </head>
    <body>
        <h1>🍳 ChefGPT Login</h1>
        <form id="loginForm">
            <div class="form-group">
                <label>Email:</label>
                <input type="email" id="email" required>
            </div>
            <div class="form-group">
                <label>Password:</label>
                <input type="password" id="password" required>
            </div>
            <button type="submit">Login</button>
            <div id="error" class="error"></div>
        </form>
        <div class="link">
            <a href="/signup">Don't have an account? Sign up</a>
        </div>
        
        <script>
            document.getElementById('loginForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const email = document.getElementById('email').value;
                const password = document.getElementById('password').value;
                const errorDiv = document.getElementById('error');
                
                try {
                    const response = await fetch('/auth/login', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ email, password })
                    });
                    
                    if (response.ok) {
                        window.location.href = '/';
                    } else {
                        const error = await response.json();
                        errorDiv.textContent = error.detail || 'Login failed';
                    }
                } catch (err) {
                    errorDiv.textContent = 'Network error. Please try again.';
                }
            });
        </script>
    </body>
    </html>
    """)


@app.get("/signup", response_class=HTMLResponse)
def signup_page():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>ChefGPT - Sign Up</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 400px; margin: 100px auto; padding: 20px; }
            .form-group { margin-bottom: 15px; }
            label { display: block; margin-bottom: 5px; }
            input { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
            button { width: 100%; padding: 10px; background: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background: #218838; }
            .error { color: red; margin-top: 10px; }
            .success { color: green; margin-top: 10px; }
            .link { text-align: center; margin-top: 15px; }
        </style>
    </head>
    <body>
        <h1>🍳 ChefGPT Sign Up</h1>
        <form id="signupForm">
            <div class="form-group">
                <label>Name:</label>
                <input type="text" id="name" required>
            </div>
            <div class="form-group">
                <label>Email:</label>
                <input type="email" id="email" required>
            </div>
            <div class="form-group">
                <label>Password (min 6 characters):</label>
                <input type="password" id="password" required minlength="6">
            </div>
            <button type="submit">Sign Up</button>
            <div id="message"></div>
        </form>
        <div class="link">
            <a href="/login">Already have an account? Login</a>
        </div>
        
        <script>
            document.getElementById('signupForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const name = document.getElementById('name').value;
                const email = document.getElementById('email').value;
                const password = document.getElementById('password').value;
                const messageDiv = document.getElementById('message');
                
                try {
                    const response = await fetch('/auth/signup', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name, email, password })
                    });
                    
                    if (response.ok) {
                        messageDiv.className = 'success';
                        messageDiv.textContent = 'Account created! Redirecting to login...';
                        setTimeout(() => window.location.href = '/login', 2000);
                    } else {
                        const error = await response.json();
                        messageDiv.className = 'error';
                        messageDiv.textContent = error.detail || 'Signup failed';
                    }
                } catch (err) {
                    messageDiv.className = 'error';
                    messageDiv.textContent = 'Network error. Please try again.';
                }
            });
        </script>
    </body>
    </html>
    """)


@app.post("/auth/signup", response_model=UserResponse)
def signup(user_data: UserSignup):
    success = db.create_user(user_data.email, user_data.password, user_data.name)
    if not success:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Get the created user
    user = db.verify_user(user_data.email, user_data.password)
    return UserResponse(**user)


@app.post("/auth/login", response_model=UserResponse)
def login(response: Response, user_data: UserLogin):
    user = login_user(response, user_data.email, user_data.password)
    return UserResponse(**user)


@app.get("/logout")
def logout(response: Response, session_token: Optional[str] = Cookie(None)):
    logout_user(response, session_token)
    return RedirectResponse(url="/login", status_code=302)


@app.get("/me", response_model=UserResponse)
def get_me(current_user: dict = Depends(require_auth)):
    return UserResponse(**current_user)


@app.post("/recipe/from_prompt", response_model=RecipeResponse)
async def recipe_from_prompt(payload: RecipeFromPromptRequest, current_user: dict = Depends(require_auth)) -> RecipeResponse:
    try:
        recipe = await generate_recipe_from_prompt(payload)
        return RecipeResponse(recipe=recipe)
    except ValidationError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        import traceback
        print(f"Error generating recipe: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Recipe generation failed: {str(e)}")


@app.post("/recipe/from_text", response_model=RecipeResponse)
async def recipe_from_text(payload: RecipeFromTextRequest, current_user: dict = Depends(require_auth)) -> RecipeResponse:
    try:
        recipe = await generate_recipe_from_text(payload)
        return RecipeResponse(recipe=recipe)
    except ValidationError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        import traceback
        print(f"Error generating recipe: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Recipe generation failed: {str(e)}")


@app.post("/recipe/from_image", response_model=RecipeResponse)
async def recipe_from_image(
    image: UploadFile = File(...),
    preferences_json: Optional[str] = Form(None),
    current_user: dict = Depends(require_auth)
):
    try:
        if preferences_json:
            # merge provided fields with sensible defaults so missing fields don't cause instantiation errors
            import json
            defaults = {
                "servings": 1,
                "cooking_time_limit_minutes": 60,
                "language": "en",
                "variation": False,
            }
            try:
                data = json.loads(preferences_json)
            except Exception:
                # if preferences_json is not valid JSON, let parse_raw raise ValidationError below
                data = None

            if isinstance(data, dict):
                merged = {**defaults, **data}
                preferences = ImageRecipePreferences(**merged)
            else:
                preferences = ImageRecipePreferences.parse_raw(preferences_json)
        else:
            preferences = ImageRecipePreferences(
                servings=1,
                cooking_time_limit_minutes=60,
                language="en",
                variation=False,
            )
    except ValidationError as ve:
        raise HTTPException(status_code=422, detail=f"Invalid preferences: {ve}")

    try:
        # Validate file size (max 25MB)
        image_bytes = await image.read()
        if len(image_bytes) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Image file too large (max 25MB)")
        
        if not image.content_type or not image.content_type.startswith('image/'):
            raise HTTPException(status_code=422, detail="Please upload a valid image file")
        
        recipe = await generate_recipe_from_image(image_bytes=image_bytes, filename=image.filename, preferences=preferences)
        return RecipeResponse(recipe=recipe)
    except HTTPException:
        raise
    except ValidationError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        import traceback
        print(f"Error processing image: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Image processing failed: {str(e)}")


@app.post("/recipes/save")
def save_recipe(payload: SaveRecipeRequest, current_user: dict = Depends(require_auth)):
    """Save a recipe for the current user"""
    try:
        import json
        recipe_data = json.dumps(payload.recipe_data.dict())
        recipe_id = db.save_recipe(current_user["id"], payload.recipe_title, recipe_data)
        return {"id": recipe_id, "message": "Recipe saved successfully"}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save recipe: {str(e)}")


@app.get("/recipes/my-recipes", response_model=SavedRecipesListResponse)
def get_my_recipes(current_user: dict = Depends(require_auth)):
    """Get all saved recipes for the current user"""
    try:
        import json
        recipes = db.get_user_recipes(current_user["id"])
        
        saved_recipes = []
        for recipe in recipes:
            recipe_dict = json.loads(recipe["recipe_data"])
            saved_recipes.append(SavedRecipeResponse(
                id=recipe["id"],
                recipe_title=recipe["recipe_title"],
                recipe_data=recipe_dict,
                created_at=recipe["created_at"]
            ))
        
        return SavedRecipesListResponse(recipes=saved_recipes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch recipes: {str(e)}")


@app.get("/recipes/my-recipes/{recipe_id}", response_model=SavedRecipeResponse)
def get_recipe(recipe_id: int, current_user: dict = Depends(require_auth)):
    """Get a specific saved recipe"""
    try:
        import json
        recipe = db.get_recipe(recipe_id, current_user["id"])
        
        if not recipe:
            raise HTTPException(status_code=404, detail="Recipe not found")
        
        recipe_dict = json.loads(recipe["recipe_data"])
        return SavedRecipeResponse(
            id=recipe["id"],
            recipe_title=recipe["recipe_title"],
            recipe_data=recipe_dict,
            created_at=recipe["created_at"]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch recipe: {str(e)}")


@app.delete("/recipes/my-recipes/{recipe_id}")
def delete_recipe(recipe_id: int, current_user: dict = Depends(require_auth)):
    """Delete a saved recipe"""
    try:
        success = db.delete_recipe(recipe_id, current_user["id"])
        
        if not success:
            raise HTTPException(status_code=404, detail="Recipe not found")
        
        return {"message": "Recipe deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete recipe: {str(e)}")


# Run with: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload


