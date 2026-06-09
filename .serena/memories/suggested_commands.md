# Suggested Commands

## Development & Execution
- **Run Locally:** `python src/main.py`
- **Lint Syntax:** `python -m py_compile src/main.py` (Checks all imports transitively).
- **Run GitHub Action Locally (if needed):** N/A, but testing GitHub Action flows requires pushing to a test branch.

## Windows Specifics
- Use `Copy-Item` instead of `cp`.
- Use `Remove-Item` instead of `rm`.
- Use `Get-ChildItem` instead of `ls`.
- Virtual environments require invoking `.\.venv\Scripts\python.exe` directly rather than standard UNIX source activation.