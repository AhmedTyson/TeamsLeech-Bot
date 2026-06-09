# Task Completion

When a task is considered completed, ensure the following steps have been explicitly taken:
1. Verify no syntax errors were introduced by running: `python -m py_compile src/main.py`.
2. Ensure any new dependencies were added to `requirements.txt`.
3. If new environment variables are required, they must be added to `AppConfig` in `src/core/config.py` using `pydantic-settings`.
4. Commit changes properly with Conventional Commits (e.g., `feat:`, `fix:`, `refactor:`, `style:`).