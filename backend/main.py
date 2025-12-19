from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, validator
from typing import Optional, List
from backend.database import init_db, get_db
import os


class AnimeCreate(BaseModel):
    title: str


class AnimeResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    average_rating: Optional[float]
    total_reviews: int
    latest_review_text: Optional[str]
    latest_review_user: Optional[str]
    created_at: str


class ReviewCreate(BaseModel):
    anime_id: int
    user_name: str
    rating: float
    review_text: Optional[str] = None
    status: str

    @validator('rating')
    def validate_rating(cls, v):
        if v < 0 or v > 10:
            raise ValueError('Rating must be between 0 and 10')
        return v

    @validator('status')
    def validate_status(cls, v):
        if v not in ['watched', 'planning']:
            raise ValueError('Status must be watched or planning')
        return v

    @validator('rating')
    def validate_rating_with_status(cls, v, values):
        if values.get('status') == 'planning' and v > 0:
            raise ValueError('Cannot rate anime with planning status')
        return v


class ReviewUpdate(BaseModel):
    rating: Optional[float] = None
    review_text: Optional[str] = None
    status: Optional[str] = None

    @validator('rating')
    def validate_rating(cls, v):
        if v is not None and (v < 0 or v > 10):
            raise ValueError('Rating must be between 0 and 10')
        return v


class ReviewResponse(BaseModel):
    id: int
    anime_id: int
    user_name: str
    rating: float
    review_text: Optional[str]
    status: str
    created_at: str


class AnimeWithReviews(BaseModel):
    anime: AnimeResponse
    reviews: List[ReviewResponse]


app = FastAPI(title="Anime Review Site")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await init_db()


@app.get("/api/anime", response_model=List[AnimeResponse])
async def get_all_anime():
    db = await get_db()
    async with db.execute("""
        SELECT 
            a.id,
            a.title,
            a. description,
            AVG(CASE WHEN r.status = 'watched' THEN r.rating ELSE NULL END) as average_rating,
            COUNT(r.id) as total_reviews,
            (SELECT review_text FROM reviews WHERE anime_id = a.id ORDER BY created_at DESC LIMIT 1) as latest_review_text,
            (SELECT user_name FROM reviews WHERE anime_id = a.id ORDER BY created_at DESC LIMIT 1) as latest_review_user,
            a.created_at
        FROM anime a
        LEFT JOIN reviews r ON a.id = r.anime_id
        GROUP BY a.id
        ORDER BY a.created_at DESC
    """) as cursor:
        rows = await cursor.fetchall()
    await db.close()
    return [dict(row) for row in rows]


@app.get("/api/anime/{anime_id}", response_model=AnimeWithReviews)
async def get_anime(anime_id: int):
    db = await get_db()

    async with db.execute("""
        SELECT 
            a. id,
            a.title,
            a.description,
            AVG(CASE WHEN r.status = 'watched' THEN r.rating ELSE NULL END) as average_rating,
            COUNT(r.id) as total_reviews,
            (SELECT review_text FROM reviews WHERE anime_id = a.id ORDER BY created_at DESC LIMIT 1) as latest_review_text,
            (SELECT user_name FROM reviews WHERE anime_id = a.id ORDER BY created_at DESC LIMIT 1) as latest_review_user,
            a.created_at
        FROM anime a
        LEFT JOIN reviews r ON a.id = r.anime_id
        WHERE a.id = ?
        GROUP BY a.id
    """, (anime_id,)) as cursor:
        anime_row = await cursor.fetchone()

    if not anime_row:
        await db.close()
        raise HTTPException(404, "Anime not found")

    async with db.execute("""
        SELECT id, anime_id, user_name, rating, review_text, status, created_at
        FROM reviews
        WHERE anime_id = ?
        ORDER BY created_at DESC
    """, (anime_id,)) as cursor:
        review_rows = await cursor.fetchall()

    await db.close()

    return {
        "anime": dict(anime_row),
        "reviews": [dict(row) for row in review_rows]
    }


@app.post("/api/anime", response_model=AnimeResponse)
async def create_anime(anime: AnimeCreate):
    db = await get_db()

    try:
        cursor = await db.execute(
            "INSERT INTO anime (title, description) VALUES (?, ?)",
            (anime.title, None)
        )
        await db.commit()
        anime_id = cursor.lastrowid
    except Exception as e:
        await db.close()
        raise HTTPException(400, "Anime with this title already exists")

    async with db.execute("""
        SELECT id, title, description, NULL as average_rating, 0 as total_reviews, NULL as latest_review_text, NULL as latest_review_user, created_at
        FROM anime WHERE id = ?
    """, (anime_id,)) as cursor:
        row = await cursor.fetchone()

    await db.close()
    return dict(row)


@app.delete("/api/anime/{anime_id}")
async def delete_anime(anime_id: int):
    db = await get_db()
    await db.execute("DELETE FROM anime WHERE id=?", (anime_id,))
    await db.commit()
    await db.close()
    return {"ok": True}


@app.post("/api/reviews", response_model=ReviewResponse)
async def create_review(review: ReviewCreate):
    db = await get_db()

    async with db.execute("SELECT id FROM anime WHERE id = ?", (review.anime_id,)) as cursor:
        anime_exists = await cursor.fetchone()

    if not anime_exists:
        await db.close()
        raise HTTPException(404, "Anime not found")

    if review.status == 'planning' and review.rating > 0:
        await db.close()
        raise HTTPException(400, "Cannot rate anime with planning status")

    cursor = await db.execute(
        "INSERT INTO reviews (anime_id, user_name, rating, review_text, status) VALUES (?, ?, ?, ?, ?)",
        (review.anime_id, review.user_name, review.rating, review.review_text, review.status)
    )
    await db.commit()

    review_id = cursor.lastrowid
    async with db.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)) as cursor:
        row = await cursor.fetchone()

    await db.close()
    return dict(row)


@app.patch("/api/reviews/{review_id}", response_model=ReviewResponse)
async def update_review(review_id: int, review_update: ReviewUpdate):
    db = await get_db()

    async with db.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)) as cursor:
        current_review = await cursor.fetchone()

    if not current_review:
        await db.close()
        raise HTTPException(404, "Review not found")

    current_status = review_update.status if review_update.status else current_review['status']
    new_rating = review_update.rating if review_update.rating is not None else current_review['rating']

    if current_status == 'planning' and new_rating > 0:
        await db.close()
        raise HTTPException(400, "Cannot rate anime with planning status")

    update_parts = []
    update_values = []

    if review_update.rating is not None:
        update_parts.append("rating = ?")
        update_values.append(review_update.rating)

    if review_update.review_text is not None:
        update_parts.append("review_text = ?")
        update_values.append(review_update.review_text)

    if review_update.status:
        update_parts.append("status = ?")
        update_values.append(review_update.status)

    if update_parts:
        update_values.append(review_id)
        query = f"UPDATE reviews SET {', '.join(update_parts)} WHERE id = ?"
        await db.execute(query, tuple(update_values))
        await db.commit()

    async with db.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)) as cursor:
        row = await cursor.fetchone()

    await db.close()
    return dict(row)


@app.delete("/api/reviews/{review_id}")
async def delete_review(review_id: int):
    db = await get_db()
    await db.execute("DELETE FROM reviews WHERE id=?", (review_id,))
    await db.commit()
    await db.close()
    return {"ok": True}


@app.get("/api/stats")
async def get_stats():
    db = await get_db()
    async with db.execute("""
        SELECT 
            LOWER(TRIM(a.title)) as normalized_title,
            a.title as display_title,
            AVG(r.rating) as average_rating,
            COUNT(r.id) as review_count
        FROM anime a
        INNER JOIN reviews r ON a.id = r.anime_id
        WHERE r.status = 'watched'
        GROUP BY normalized_title
        HAVING COUNT(r.id) > 0
        ORDER BY average_rating DESC
    """) as cursor:
        rows = await cursor.fetchall()
    await db.close()

    result = []
    for row in rows:
        result.append({
            "title": row['display_title'],
            "average_rating": row['average_rating'],
            "review_count": row['review_count']
        })

    return result


@app.get("/")
async def root():
    return {"message": "Anime Review Site API"}


frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")