"""Example FastAPI routes for testing."""

from fastapi import APIRouter, FastAPI

app = FastAPI()
router = APIRouter(prefix="/api")


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Hello World"}


@router.get("/users")
async def list_users():
    """List all users."""
    return []


@router.get("/users/{user_id}")
async def get_user(user_id: int):
    """Get a specific user by ID."""
    return {"id": user_id}


@router.post("/users")
async def create_user(user: dict):
    """Create a new user."""
    return user


@router.delete("/users/{user_id}")
async def delete_user(user_id: int):
    """Delete a user by ID."""
    return {"deleted": user_id}


app.include_router(router)
