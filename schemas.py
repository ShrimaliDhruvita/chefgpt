from __future__ import annotations

from pydantic import BaseModel, Field, conlist, validator
from typing import List, Optional, Literal


class HealthResponse(BaseModel):
    status: Literal["ok"]


class NutritionFacts(BaseModel):
    calories: Optional[int] = Field(None, ge=0)
    protein_g: Optional[float] = Field(None, ge=0)
    carbs_g: Optional[float] = Field(None, ge=0)
    fat_g: Optional[float] = Field(None, ge=0)
    fiber_g: Optional[float] = Field(None, ge=0)
    sodium_mg: Optional[float] = Field(None, ge=0)


class Step(BaseModel):
    number: int = Field(..., ge=1)
    instruction: str


class Ingredient(BaseModel):
    name: str
    quantity: Optional[str] = None  # free text like "1 cup", "200 g"


class Recipe(BaseModel):
    title: str
    cuisine: Optional[str] = None
    servings: int = Field(..., ge=1)
    total_time_minutes: Optional[int] = Field(None, ge=0)
    ingredients: List[Ingredient]
    steps: List[Step]
    nutrition: Optional[NutritionFacts] = None
    tips: Optional[List[str]] = None


class DietaryPreference(BaseModel):
    vegetarian: Optional[bool] = None
    vegan: Optional[bool] = None
    gluten_free: Optional[bool] = None
    dairy_free: Optional[bool] = None
    nut_free: Optional[bool] = None
    low_carb: Optional[bool] = None
    high_protein: Optional[bool] = None


class RecipeFromTextRequest(BaseModel):
    ingredients: conlist(str, min_items=1)  # e.g. ["aloo", "matar"]
    servings: Optional[int] = Field(2, ge=1)
    dietary: Optional[DietaryPreference] = None
    cuisine_hint: Optional[str] = Field(None, description="e.g. Indian, Italian")
    cooking_time_limit_minutes: Optional[int] = Field(None, ge=1)
    language: Optional[str] = Field("english", description="Language for the recipe response")
    variation: Optional[bool] = Field(False, description="Generate a different/unique variation of the recipe")

    @validator("ingredients")
    def normalize_ingredients(cls, v: List[str]) -> List[str]:
        return [item.strip() for item in v if item and item.strip()]

    @validator("language")
    def normalize_language(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        normalized = value.strip().lower()
        return normalized if normalized else None


class ImageRecipePreferences(BaseModel):
    servings: Optional[int] = Field(2, ge=1)
    dietary: Optional[DietaryPreference] = None
    cuisine_hint: Optional[str] = None
    cooking_time_limit_minutes: Optional[int] = Field(None, ge=1)
    language: Optional[str] = Field("english", description="Language for the recipe response")
    variation: Optional[bool] = Field(False, description="Generate a different/unique variation of the recipe")

    @validator("language")
    def normalize_language(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        normalized = value.strip().lower()
        return normalized if normalized else None


class RecipeResponse(BaseModel):
    recipe: Recipe


class UserSignup(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., regex=r'^[^@]+@[^@]+\.[^@]+$')
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: int
    name: str
    email: str


class RecipeFromPromptRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=500)
    servings: Optional[int] = Field(2, ge=1)
    language: Optional[str] = Field("english", description="Language for the recipe response")
    variation: Optional[bool] = Field(False, description="Generate a different/unique variation of the recipe")


class SaveRecipeRequest(BaseModel):
    recipe_title: str = Field(..., min_length=1, max_length=200)
    recipe_data: Recipe


class SavedRecipeResponse(BaseModel):
    id: int
    recipe_title: str
    recipe_data: Recipe
    created_at: str


class SavedRecipesListResponse(BaseModel):
    recipes: List[SavedRecipeResponse]

