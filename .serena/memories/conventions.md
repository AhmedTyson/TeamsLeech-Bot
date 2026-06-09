# Code Conventions

- **Strict Typing:** All data models must use Pydantic `BaseModel`. No raw Python dictionaries for business entities.
- **Asynchronous IO:** All network operations MUST be async. Use `httpx.AsyncClient` instead of `requests`. Use `asyncio.to_thread` only for blocking subprocesses (like `ffmpeg`).
- **Dependency Injection:** Telegram handlers in `src/tg_bot/handlers/` do not instantiate their own services. Services (`ScannerService`, `TransferService`, `StateManager`) are created in `main.py` and passed into the `register_all_handlers` function.
- **Error Handling:** Do not silently fail. Use custom exceptions (e.g., `GraphAPIError`, `TokenExpiredError`) and catch them at the presentation layer (Telegram handlers) to notify the user gracefully.
- **State Management:** The global application state MUST NOT rely on mutable module-level dictionaries. Always use `StateManager.get_session(user_id)` to access the `UserSession` Pydantic model for UI state tracking.