import aiosqlite
import os

DB_PATH = os.getenv('DB_PATH', 'anime.db')


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS anime (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anime_id INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                rating REAL NOT NULL CHECK(rating >= 0 AND rating <= 10),
                review_text TEXT,
                status TEXT NOT NULL CHECK(status IN ('watched', 'planning')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (anime_id) REFERENCES anime(id) ON DELETE CASCADE
            )
        """)

        await db.commit()


async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db