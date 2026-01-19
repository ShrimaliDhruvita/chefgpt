## ChefGPT (FastAPI)

Minimal API to generate nutrition-aware, customized recipes from ingredients or an image.

### Setup
1. Create and activate a virtual environment.
2. `pip install -r requirements.txt`
3. Create a `.env` file in project root with your Gemini API key:
  
  ```env
  GEMINI_API_KEY=your-gemini-key-here
  ```
  Get your free API key at: https://aistudio.google.com/app/apikey
  
  Never commit `.env` to git.
4. Run (auto-opens browser): `python run.py`
   
   Or manually: `uvicorn app.main:app --reload` and open `http://localhost:8000/`.

Open docs at `http://localhost:8000/docs`.

### Endpoints
- `GET /health` – service status
- `POST /recipe/from_text` – JSON body with ingredients and preferences
- `POST /recipe/from_image` – multipart form with `image` file and optional `preferences_json`

### Notes
- Model: `gemini-2.0-flash` for both text and image analysis (FREE & FAST)
- Responses are structured into a `recipe` object with ingredients, steps, and nutrition facts.

