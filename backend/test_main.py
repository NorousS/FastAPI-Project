import pytest
import os
from httpx import AsyncClient
from main import app
from database import init_db

os.environ['DB_PATH'] = 'test_anime. db'


@pytest.fixture(autouse=True)
async def setup_db():
    if os.path.exists('test_anime.db'):
        os.remove('test_anime.db')
    await init_db()
    yield
    if os.path.exists('test_anime.db'):
        os.remove('test_anime.db')


@pytest.mark.asyncio
async def test_create_anime():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/anime", json={
            "title": "Naruto",
            "description": "Ninja story"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Naruto"


@pytest.mark.asyncio
async def test_create_review():
    async with AsyncClient(app=app, base_url="http://test") as client:
        anime_response = await client.post("/api/anime", json={
            "title": "One Piece",
            "description": "Pirate adventure"
        })
        anime_id = anime_response.json()["id"]

        review_response = await client.post("/api/reviews", json={
            "anime_id": anime_id,
            "user_name": "John",
            "rating": 9.5,
            "review_text": "Amazing anime",
            "status": "watched"
        })
        assert review_response.status_code == 200
        assert review_response.json()["rating"] == 9.5


@pytest.mark.asyncio
async def test_cannot_rate_planning():
    async with AsyncClient(app=app, base_url="http://test") as client:
        anime_response = await client.post("/api/anime", json={
            "title": "Attack on Titan"
        })
        anime_id = anime_response.json()["id"]

        review_response = await client.post("/api/reviews", json={
            "anime_id": anime_id,
            "user_name": "Jane",
            "rating": 8.0,
            "status": "planning"
        })
        assert review_response.status_code == 400