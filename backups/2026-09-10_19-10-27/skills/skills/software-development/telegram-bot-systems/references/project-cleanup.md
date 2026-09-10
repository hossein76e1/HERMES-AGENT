# Project Cleanup Reference (from sessions 2026-09-06/07)

**Context**: Disk hit 100% (434M VPS). User requested cleanup of all non-essential projects, keeping only the order system (support + admin).

## Round 1 — project files deleted (2026-09-06)
From `/data/workspace/projects/`:
- Bots: appointment_bot, auto_reply_bot, competitor_monitor, content_generator, dashboard, email_automation, order_bot, price_comparison, survey_bot, image_service
- System: auto_builder.py (later restored — it IS part of the order pipeline), test_e2e_flow, test_e2e_v2–v5, test_lifecycle, test_support
- Data dirs: receipts/, survey_data/, competitor_data/, dashboard_data/

Preserved: `.last_seen_order_id`, `order_flow.py`, `support_bot.py`, `/data/workspace/order-system/` (never touch).

## Round 2 — disk still 100%: the real eater was the backup repo
- `/data/hermes-backup-repo` had grown to **272M**: every 12h backup made a full dir + tarball (~30M each, 10 retained) → ~200M in `backups/`, plus 66M `.git`.
- Fix: keep only last **3** local backup dirs for BOTH `backups/` and `projects-backup/`, prune orphan tarballs, git gc. Result: 100% → 66–72%.
- `git gc --prune=now` fails `Out of diskspace` on a full disk (repack needs room) → prune dirs FIRST, clean `.git/objects/*/tmp_obj_*` + `tmp_pack_*`, then gc.
- disk_monitor.sh upgraded: cron every 30m, threshold 80%, runs retention itself, exits 2 with a Persian warning if cleanup can't get under 80% (agent must warn owner; never delete memories/workspace/backups unasked).

## Procedure (validated)
1. `du -sh /data/*` + `df -h /data` — find the real eater before deleting code (it was backups, not projects).
2. Delete only workspace project files; expect Tirith approval on burst deletions (>10 files/20s).
3. Verify: `ls /data/workspace/projects/` → `.last_seen_order_id`, `order_flow.py`, `support_bot.py` (+ `auto_builder.py`/`survey_bot.py` as restored).
4. Backup repo retention: keep 3 dirs each side, `rm` orphan tarballs, `git gc --prune=now`.
5. **Anything deleted is recoverable from git history** of `hermes-backup-repo` (commit `8f05700` and later carry full trees) — tell the owner this before deleting, it de-risks the decision.
6. Owner retracted one deletion («پشیمون شدم») — auto_builder came back on request. Always offer restore; keep the inventory list in memory.
