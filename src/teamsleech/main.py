import logging
import os

from pyrogram import Client

from teamsleech.core.config import settings
from teamsleech.services.auth import TokenExpiredError, authenticate
from teamsleech.services.discovery import DiscoveryService
from teamsleech.services.graph import GraphClient
from teamsleech.services.reauth import run_reauth_flow
from teamsleech.services.scanner import ScannerService, validate_keyword_lists
from teamsleech.services.state import StateManager
from teamsleech.services.transfer import TransferService
from teamsleech.tg_bot.handlers import register_all_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-14s  %(levelname)-5s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")

async def _verify_matching(app, discovery, scanner, chat_id: int) -> None:
    """Dry-run matcher against ALL real data: report teams per subject."""
    subjects = scanner.load_subjects()
    if not subjects:
        await app.send_message(chat_id, "❌ Verify: no subjects configured.")
        return
    try:
        teams = await discovery.get_all_joined_teams()
    except Exception as e:
        await app.send_message(chat_id, f"❌ Verify: teams fetch failed: {e}")
        return

    lines = [
        f"🔍 **Matching verify** — {len(subjects)} subjects, {len(teams)} teams:"
    ]
    team_hits: dict[str, list[str]] = {}
    for subj in subjects:
        matched = scanner._match_teams(teams, subj)
        doc = f" + 👨‍🏫 {subj.doctor}" if subj.doctor else ""
        lines.append(f"\n📚 **{subj.name}**{doc}: {len(matched)} team(s)")
        for err in validate_keyword_lists(subj.keywords, subj.doctor_keywords):
            lines.append(f"   ⚠️ config: {err}")
        for t in matched:
            lines.append(f"   - `{t.display_name}`")
            team_hits.setdefault(t.id, []).append(subj.name)
        if not matched:
            lines.append("   ⚠️ zero teams — keywords match nothing!")
            suggestions = scanner.suggest_teams(subj, teams)
            if suggestions:
                lines.append(
                    "   💡 maybe you meant: "
                    + "; ".join(f"`{t.display_name}`" for t in suggestions)
                )

    dupes = {tid: names for tid, names in team_hits.items() if len(names) > 1}
    if dupes:
        lines.append("\n⚠️ **Cross-matched teams** (bleed check):")
        id2name = {t.id: t.display_name for t in teams}
        for tid, names in dupes.items():
            lines.append(f"   - `{id2name.get(tid, tid)}` → {', '.join(names)}")
    else:
        lines.append("\n✅ No cross-matched teams.")

    try:
        results = await scanner.scan_recordings()
    except Exception as e:
        lines.append(f"\n❌ Scan failed: {e}")
        results = {}
    if results:
        lines.append("\n🎞 **Recordings grabbed per subject:**")
        for subj in subjects:
            recs = results.get(subj.name, [])
            n_vid = sum(1 for r in recs if r.is_video)
            n_doc = len(recs) - n_vid
            got_teams = sorted({r.team_name for r in recs})
            if recs:
                lines.append(
                    f"   - **{subj.name}**: {n_vid} 🎬 + {n_doc} 📄"
                    f" from {', '.join(got_teams)}"
                )
            else:
                lines.append(f"   - **{subj.name}**: nothing found")

    lines.append("\n📦 **Drive search depth (.mp4 first page):**")
    for subj in subjects:
        matched = scanner._match_teams(teams, subj)
        for team in matched:
            for drive in await scanner.team_all_drives(team):
                try:
                    count, truncated = await scanner.drive_mp4_stats(drive["id"])
                except Exception as e:
                    lines.append(f"   - {team.display_name}: stats failed: {e}")
                    continue
                flag = " ⚠️ TRUNCATED — pages lost!" if truncated else ""
                lines.append(
                    f"   - {team.display_name} / {drive.get('name')}:"
                    f" {count} hits{flag}"
                )
                try:
                    status, n_mp4, more = await scanner.drive_recordings_folder_stats(
                        drive["id"]
                    )
                except Exception as e:
                    lines.append(f"      folder check failed: {e}")
                    continue
                more_flag = " (+more pages!)" if more else ""
                lines.append(
                    f"      📁 Recordings folder: {status},"
                    f" {n_mp4} .mp4{more_flag}"
                )

    lines.append("\n👤 **Your OneDrive (group-call recordings live here):**")
    try:
        od_search = await scanner.graph.get("/me/drive/root/search(q='.mp4')")
        od_hits = od_search.get("value", [])
        od_truncated = "@odata.nextLink" in od_search
        od_names = sorted(
            {str(i.get("name", "")) for i in od_hits if i.get("name")}
        )
        lines.append(
            f"   - {len(od_hits)} .mp4 hits"
            f"{' ⚠️ TRUNCATED' if od_truncated else ''}"
        )
        for n in od_names[:15]:
            lines.append(f"     - `{n}`")
        if len(od_names) > 15:
            lines.append(f"     - …and {len(od_names) - 15} more")
    except Exception as e:
        lines.append(f"   - OneDrive check failed: {e}")
    lines.append(
        "   _Other doctors' OneDrives need their own login — not reachable"
        " with this session._"
    )

    text = "\n".join(lines)
    log.info("Verify report:\n%s", text)
    await app.send_message(chat_id, text[:4000])

def main():
    log.info("=" * 50)
    log.info("TeamsLeech Modern App — Booting")
    log.info("=" * 50)

    # 1. Initialize Pyrogram Client
    app = Client(
        name="teamsleech_bot",
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        bot_token=settings.telegram_bot_token,
        in_memory=True,
    )

    async def _run():
        # 2. Authenticate & Rotate Secret
        log.info("Step 1/3: Authenticating with Microsoft & GitHub...")
        try:
            access_token = await authenticate()
        except TokenExpiredError:
            log.critical("Microsoft session expired. Please run local setup script and update TEAMS_REFRESH_TOKEN secret.")
            # Start dummy bot mode to send alert if possible?
            return
        except Exception as e:
            log.critical(f"Auth failed: {e}")
            return
            
        # 3. Initialize Services
        log.info("Step 2/3: Initializing core services...")
        graph_client = GraphClient(access_token)
        try:
            me = await graph_client.get("/me?$select=displayName,userPrincipalName,id")
            log.info(
                "Acting as: %s (%s)",
                me.get("displayName"), me.get("userPrincipalName"),
            )
        except Exception as e:
            log.warning("Could not read /me: %s", e)
        state_manager = StateManager(app, settings.telegram_chat_id)
        discovery_service = DiscoveryService(graph_client)
        scanner_service = ScannerService(graph_client, state_manager)
        transfer_service = TransferService(graph_client, state_manager, app, settings.telegram_chat_id)
        
        # 4. Register Handlers
        register_all_handlers(
            app,
            scanner=scanner_service,
            transfer=transfer_service,
            state=state_manager,
            discovery=discovery_service
        )
        
        await app.start()

        run_mode = os.getenv("RUN_MODE", "normal")
        if run_mode == "reauth":
            log.info("Reauth mode: starting Microsoft device-code login...")
            await run_reauth_flow(app, settings.telegram_chat_id)
        elif run_mode == "verify":
            await _verify_matching(
                app, discovery_service, scanner_service,
                settings.telegram_chat_id,
            )
            await graph_client.close()
            await app.stop()
            return

        log.info("Step 3/3: Bot is live and listening.")
        
        # 5. Scheduled Auto-Check Logic (Silent Mode)
        if settings.auto_check == "1":
            log.info("Running automated scheduled check...")

            subject_filter = os.getenv("SUBJECT_NAME") or None
            if subject_filter:
                log.info("Filtering to single subject: %s", subject_filter)

            try:
                results = await scanner_service.scan_recordings(subject_filter, None, None)
                total = sum(len(recs) for recs in results.values())
                if total > 0:
                    from teamsleech.tg_bot.keyboards import build_checklist_keyboard
                    from teamsleech.tg_bot.views import build_checklist_text, videos_first

                    label = "All Recordings"
                    session = state_manager.get_session(settings.telegram_chat_id)
                    for subj_name in results:
                        results[subj_name] = videos_first(results[subj_name])
                    session.pending_recordings = [r for recs in results.values() for r in recs]
                    session.scan_label = label

                    doctors = {s.name: s.doctor for s in scanner_service.load_subjects()}
                    text = build_checklist_text(results, label, doctors=doctors)
                    keyboard = build_checklist_keyboard(session.pending_recordings, session.selected_indices)

                    await app.send_message(settings.telegram_chat_id, text, reply_markup=keyboard)
                    log.info("Auto-check found %d recordings, notification sent.", total)
                else:
                    log.info("Auto-check found 0 new recordings. Staying completely silent.")
            except Exception as e:
                log.error("Scheduled check failed: %s", e)

        from pyrogram import idle
        await idle()
        
        # Cleanup
        await graph_client.close()
        await app.stop()

    app.run(_run())

if __name__ == "__main__":
    main()
