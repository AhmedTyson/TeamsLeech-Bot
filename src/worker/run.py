"""On-demand worker: folders -> new files -> Telegram -> state. No Azure."""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from worker import config as config_mod
from worker import state as state_mod
from worker.downloader import download, download_url
from worker.lister import FileEntry, list_folder
from worker.telegram import notify, upload_file


@dataclass
class FetchResult:
    folder: str
    name: str
    size: int
    tg_msg_id: int | None


def load_cookies(path: str) -> list[dict[str, Any]]:
    from http.cookiejar import MozillaCookieJar

    jar = MozillaCookieJar(path)
    jar.load(ignore_discard=True, ignore_expires=True)
    return [{"name": c.name, "value": c.value or ""} for c in jar]


def site_base(folder_url: str) -> str:
    parsed = urlparse(folder_url)
    return f"{parsed.scheme}://{parsed.hostname}"


def entry_key(entry: FileEntry) -> str:
    return entry.unique_id or entry.server_path or entry.name


ListFn = Callable[[str, list[dict[str, Any]], httpx.Client], list[FileEntry]]
DownloadFn = Callable[[str, list[dict[str, Any]], str, httpx.Client], tuple[int, str]]
UploadFn = Callable[[str, str], Awaitable[int | None]]
NotifyFn = Callable[[str], int | None]


async def run(
    state_path: str,
    tmp_dir: str,
    list_fn: ListFn | None = None,
    download_fn: DownloadFn | None = None,
    upload_fn: UploadFn | None = None,
    notify_fn: NotifyFn | None = None,
) -> list[FetchResult]:
    folders = config_mod.load_folders()
    cookies = load_cookies(os.environ.get("MS_COOKIES_FILE", "cookies.txt"))
    if not cookies:
        msg = "No cookies loaded: re-bootstrap MS_COOKIES."
        raise ValueError(msg)
    state = state_mod.load(state_path)
    list_fn = list_fn or list_folder
    download_fn = download_fn or download
    upload_fn = upload_fn or upload_file
    notify_fn = notify_fn or notify
    results: list[FetchResult] = []
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"
    with httpx.Client() as client:
        for folder in folders:
            try:
                entries = await asyncio.to_thread(list_fn, folder.url, cookies, client)
            except PermissionError as exc:
                print(f"listing failed for {folder.name}: {exc}")
                notify_fn(f"Session expired listing {folder.name}: {exc}")
                continue
            print(f"listed {len(entries)} entries in {folder.name}")
            fresh = [e for e in entries if state_mod.is_new(entry_key(e), state)]
            if dry_run:
                for entry in fresh:
                    print(f"would fetch: {folder.name}: {entry.name} ({entry.size} bytes)")
                    results.append(FetchResult(folder.name, entry.name, entry.size, None))
                continue
            for entry in fresh:
                dest = os.path.join(tmp_dir, entry.name)
                try:
                    size, _ = await asyncio.to_thread(
                        download_fn,
                        download_url(site_base(folder.url), entry.unique_id)
                        if entry.unique_id
                        else folder.url + "/" + entry.name,
                        cookies,
                        dest,
                        client,
                    )
                except PermissionError as exc:
                    print(f"download failed for {entry.name}: {exc}")
                    notify_fn(f"Session expired downloading {entry.name}: {exc}")
                    continue
                msg_id = await upload_fn(dest, entry.name)
                state_mod.mark(state, entry_key(entry), entry.name, msg_id)
                state_mod.save(state, state_path)
                results.append(FetchResult(folder.name, entry.name, size, msg_id))
    if results and not dry_run:
        lines = [f"New content detected ({len(results)}):"]
        lines += [f"- {r.folder}: {r.name}" for r in results]
        notify_fn("\n".join(lines))
    elif not results:
        print("No new files.")
    return results


def main() -> None:
    state_path = os.environ.get("WORKER_STATE", "state/processed.json")
    tmp_dir = tempfile.mkdtemp(prefix="worker-")
    results = asyncio.run(run(state_path, tmp_dir))
    print(f"done: {len(results)} new files")


if __name__ == "__main__":
    main()
