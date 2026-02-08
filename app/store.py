import json
import aiosqlite
from datetime import datetime
from typing import Any
from chatkit.store import Store, AttachmentStore, NotFoundError
from chatkit.types import (
    ThreadMetadata, ThreadItem, Page, Attachment, 
    AttachmentCreateParams
)
from pydantic import TypeAdapter
from .types import RequestContext

DB_PATH = "chatkit.db"

class SQLiteStore(Store[RequestContext], AttachmentStore[RequestContext]):
    def __init__(self):
        self.db = None

    async def connect(self):
        self.db = await aiosqlite.connect(DB_PATH)
        # Enable WAL mode for better concurrency performance
        await self.db.execute("PRAGMA journal_mode=WAL;")
        await self._init_db()

    async def close(self):
        if self.db:
            await self.db.close()

    async def _init_db(self):
        async with self.db.execute("BEGIN"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS threads (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    data TEXT NOT NULL
                )
            """)
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    data TEXT NOT NULL,
                    FOREIGN KEY(thread_id) REFERENCES threads(id) ON DELETE CASCADE
                )
            """)
            await self.db.execute("CREATE INDEX IF NOT EXISTS idx_items_thread ON items(thread_id);")
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS attachments (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    data TEXT NOT NULL
                )
            """)
            await self.db.commit()

    # --- Thread Operations ---

    async def load_thread(self, thread_id: str, context: RequestContext) -> ThreadMetadata:
        async with self.db.execute(
            "SELECT data FROM threads WHERE id = ? AND user_id = ?", 
            (thread_id, context.user_id)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                raise NotFoundError(f"Thread {thread_id} not found")
            return ThreadMetadata.model_validate_json(row[0])

    async def save_thread(self, thread: ThreadMetadata, context: RequestContext) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO threads (id, user_id, created_at, data) VALUES (?, ?, ?, ?)",
            (thread.id, context.user_id, thread.created_at.isoformat(), thread.model_dump_json())
        )
        await self.db.commit()

    async def load_threads(self, limit: int, after: str | None, order: str, context: RequestContext) -> Page[ThreadMetadata]:
        # Simple pagination: Get all (optimized would use OFFSET/LIMIT in SQL)
        query = "SELECT data FROM threads WHERE user_id = ? ORDER BY created_at DESC"
        async with self.db.execute(query, (context.user_id,)) as cursor:
            rows = await cursor.fetchall()
            
        threads = [ThreadMetadata.model_validate_json(r[0]) for r in rows]
        
        start_idx = 0
        if after:
            for i, t in enumerate(threads):
                if t.id == after:
                    start_idx = i + 1
                    break
        
        sliced = threads[start_idx : start_idx + limit]
        has_more = (start_idx + limit) < len(threads)
        new_after = sliced[-1].id if sliced and has_more else None
        
        return Page(data=sliced, has_more=has_more, after=new_after)

    async def delete_thread(self, thread_id: str, context: RequestContext) -> None:
        await self.db.execute("DELETE FROM threads WHERE id = ? AND user_id = ?", (thread_id, context.user_id))
        await self.db.execute("DELETE FROM items WHERE thread_id = ? AND user_id = ?", (thread_id, context.user_id))
        await self.db.commit()

    # --- Item Operations ---

    async def load_thread_items(self, thread_id: str, after: str | None, limit: int, order: str, context: RequestContext) -> Page[ThreadItem]:
        # Validate ownership
        async with self.db.execute("SELECT 1 FROM threads WHERE id = ? AND user_id = ?", (thread_id, context.user_id)) as cursor:
            if not await cursor.fetchone():
                raise NotFoundError("Thread not found")

        # Get items
        async with self.db.execute(
            "SELECT data FROM items WHERE thread_id = ? ORDER BY created_at ASC", 
            (thread_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            
        adapter = TypeAdapter(ThreadItem)
        items = [adapter.validate_json(r[0]) for r in rows]
        
        if order == "desc":
            items.reverse()

        start_idx = 0
        if after:
            for i, item in enumerate(items):
                if item.id == after:
                    start_idx = i + 1
                    break
        
        sliced = items[start_idx : start_idx + limit]
        has_more = (start_idx + limit) < len(items)
        new_after = sliced[-1].id if sliced and has_more else None

        return Page(data=sliced, has_more=has_more, after=new_after)

    async def add_thread_item(self, thread_id: str, item: ThreadItem, context: RequestContext) -> None:
        await self.db.execute(
            "INSERT INTO items (id, thread_id, user_id, created_at, data) VALUES (?, ?, ?, ?, ?)",
            (item.id, thread_id, context.user_id, item.created_at.isoformat(), item.model_dump_json())
        )
        await self.db.commit()

    async def save_item(self, thread_id: str, item: ThreadItem, context: RequestContext) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO items (id, thread_id, user_id, created_at, data) VALUES (?, ?, ?, ?, ?)",
            (item.id, thread_id, context.user_id, item.created_at.isoformat(), item.model_dump_json())
        )
        await self.db.commit()

    async def load_item(self, thread_id: str, item_id: str, context: RequestContext) -> ThreadItem:
        async with self.db.execute("SELECT data FROM items WHERE id = ? AND thread_id = ?", (item_id, thread_id)) as cursor:
            row = await cursor.fetchone()
            if not row:
                raise NotFoundError(f"Item {item_id} not found")
            return TypeAdapter(ThreadItem).validate_json(row[0])

    async def delete_thread_item(self, thread_id: str, item_id: str, context: RequestContext) -> None:
        await self.db.execute("DELETE FROM items WHERE id = ? AND thread_id = ?", (item_id, thread_id))
        await self.db.commit()

    # --- Attachment Operations ---

    async def save_attachment(self, attachment: Attachment, context: RequestContext) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO attachments (id, user_id, data) VALUES (?, ?, ?)",
            (attachment.id, context.user_id, attachment.model_dump_json())
        )
        await self.db.commit()

    async def load_attachment(self, attachment_id: str, context: RequestContext) -> Attachment:
        async with self.db.execute("SELECT data FROM attachments WHERE id = ?", (attachment_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                raise NotFoundError(f"Attachment {attachment_id} not found")
            return TypeAdapter(Attachment).validate_json(row[0])

    async def delete_attachment(self, attachment_id: str, context: RequestContext) -> None:
        await self.db.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
        await self.db.commit()
    
    async def create_attachment(self, input: AttachmentCreateParams, context: RequestContext) -> Attachment:
        raise NotImplementedError("Using direct upload strategy")