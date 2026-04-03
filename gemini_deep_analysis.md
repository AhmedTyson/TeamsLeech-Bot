# TeamsLeech Bot — Comprehensive Deep Analysis & Optimization Vector Report

This document is specifically structured for AI context ingestion (such as Google Gemini). Its purpose is to provide a comprehensive, deep-dive analysis of the **TeamsLeech Bot**, a Python-based Telegram bot architecture, in order to research, strategize, and determine the absolute "best of the best" software engineering solutions for maximum performance, quality, and stability.

---

## 1. System Overview & Context

**Objective:** The TeamsLeech Bot automatically scans an authenticated user's university Microsoft Teams environment (via MS Graph API) for new lecture video recordings (`.mp4`), downloads them, and acts as a bridge pipeline to permanently archive them into Telegram Saved Messages.

**Current Tech Stack:**
- **Language:** Python 3.11+
- **APIs:** Microsoft Graph API (httpx/asyncio), Telegram Bot API/MTProto (Pyrogram)
- **Deployment:** GitHub Actions (`ubuntu-latest` free tier), triggered manually via `workflow_dispatch`. Max timeout: 30 minutes.
- **State Management:** Ephemeral. Token state is stored via GitHub Secrets (periodically rotated by a local script).

---

## 2. Current Architectural Workflows

1. **Auth & Identity:** Validates Telegram env vars. Microsoft Graph Graph API Bearer token is loaded from `TEAMS_REFRESH_TOKEN`.
2. **Asynchronous Fetching (`fetcher.py`):** Uses an asynchronous HTTP client (`httpx.AsyncClient`) to scan `/me/joinedTeams`, paginates through teams, maps them to `subjects_config.json`, concurrently fetches drives, and searches for `.mp4` items using highly parallel `asyncio.gather` tasks.
3. **User Interaction (`bot.py`):** Pyrogram handlers serve an interactive checklist via inline keyboards. Users can rename files, select multiple files, and confirm the batched upload. It features local text truncation and strict button length capping (Telegram limits).
4. **Download & Upload Pipeline (`uploader.py`):** 
    - *Download Phase:* Downloads the selected file from MS Graph API to the local runner filesystem (`/tmp/`).
    - *Metadata Phase:* Runs `ffprobe` (via `subprocess`) to reliably extract video headers (height/width/duration) for Telegram's native player UI.
    - *Upload Phase:* Uses Pyrogram MTProto to stream the `.mp4` from the local `/tmp/` directory to Telegram servers up to the absolute 2GB limit (which bypasses the 50MB HTTP Bot Upload limits).

---

## 3. Core Identified Bottlenecks & Limitations

To evolve this architecture into a state-of-the-art service, the following bottlenecks must be addressed:

### A. I/O and Disk Bound Operations 
The current process requires 100% of the file to be downloaded to local disk *before* Telegram starts receiving it. This results in **2x time latency** and necessitates allocating unnecessary disk space on the GitHub Action ephemeral runner environment. 

### B. Ephemeral Execution Environment Constraints
Running the bot locally under GitHub Actions means it suffers from "Amnesia". There is no local database storage; consequently, the timeline for `last_run` state processing relies on manual input instead of intelligent internal state caching.

### C. Sequential Network Processing
The video queue uploads strictly sequentially: `[Queue: Vid A, Vid B] -> Download Vid A -> Upload Vid A -> Download Vid B...`. This leaves the download bandwidth at `0mbps` while uploading, and upload bandwidth at `0mbps` while downloading. It does not exploit the server's full-duplex network interface.

### D. Security & Token Entropy
Managing the MS Graph `TEAMS_REFRESH_TOKEN` currently requires giving automated pipelines full GitHub Personal Access Token (`GH_PAT`) rights to rotate the repository secret. This creates an unnecessary attack vector on the source codebase infrastructure.

---

## 4. Primary Research Vectors (For Gemini Deep-Analysis)

**AI Prompt / Objective:** Analyze the factors above and formulate the most highly optimized, best-in-class implementation paths for the following architectural pivots:

### Research Vector 1: Direct Memory Pipe Streaming
- **Question:** What is the most Pythonic and stable method to pipe an async byte-stream response (`httpx`) from Graph API *directly* into Pyrogram's MTProto chunked `send_video` mechanism? 
- **Constraints:** Pyrogram traditionally requires a known `file_size` and a file-like seekable object buffer (e.g. `io.BytesIO`) to calculate and send MTProto chunks. For a 1.5 GB video, caching to `BytesIO` will trigger an Out-Of-Memory (OOM) error. How can we patch Pyrogram's `FileId` or use an asynchronous FIFO buffer stream generator to mimic a file-like object while achieving a continuous pipe?

### Research Vector 2: Achieving 100% Network Saturation (Concurrency)
- **Question:** How do we effectively balance a `Producer` / `Consumer` task queue in Python `asyncio` for maximizing full-duplex throughput? 
- **Goal:** Designing an asynchronous worker pool where Worker A handles downloading the *next* video concurrently while Worker B is uploading the *current* video to Telegram without triggering Telegram's notorious `420 FloodWait` errors. 

### Research Vector 3: Zero-Cost Serverless State Storage
- **Question:** Given the desire to keep infrastructure costs at zero, what is the best paradigm for storing relational or key-value data persistently? 
- **Idea to Explore:** Can we use a hidden private Telegram Channel as a NoSQL datastore (storing base64 encoded JSON text messages)? What are the caching models and performance limits versus utilizing external free tiers like Supabase, MongoDB Atlas Free, or Cloudflare KV?

### Research Vector 4: PaaS / Deployment Paradigms
- **Question:** Does executing a Telegram MTProto application via GitHub Actions (with manual triggers and short timeouts) remain viable long-term? What low-latency, "always-on" free-tier hosting alternatives (Render, Railway, Fly.io) provide sufficient memory and compute constraints for our Graph UI scraping task, assuming we pivot to Webhook or efficient Long-Polling paradigms?

---

## 5. Definition of Done (Metrics for Maximum Quality)

The final architecture will be considered "Best of the Best" when:
1. **Zero-Disk Streaming:** The local machine utilizes `<50MB` RAM/Disk while processing a `2GB` video file.
2. **Latency:** Total bridge time approaches the `Max(DownloadSpeed, UploadSpeed)` rather than `DownloadSpeed + UploadSpeed`.
3. **Stateless Reusability:** The application can crash, restart, and perfectly resume upload progress natively referencing previous cloud-stored state timelines.
