# Project Cleanup Reference (from session)

**Context**: Disk space was critically low (112M in `.hermes/`, 536K in workspace projects). User requested cleanup of all non-essential projects, keeping only the order-system.

**What was deleted** (from `/data/workspace/projects/`):
- `appointment_bot.py`
- `auto_builder.py`
- `auto_reply_bot.py`
- `competitor_monitor.py`
- `content_generator.py`
- `dashboard.py`
- `email_automation.py`
- `image_service.py`
- `order_bot.py`
- `price_comparison.py`
- `survey_bot.py`
- `test_e2e_flow.py`
- `test_e2e_v2.py`
- `test_e2e_v3.py`
- `test_e2e_v4.py`
- `test_e2e_v5.py`
- `test_lifecycle.py`
- `test_support.py`
- `competitor_data/` directory
- `dashboard_data/` directory
- `receipts/` directory
- `survey_data/` directory

**What was preserved**:
- `/data/workspace/projects/.last_seen_order_id`
- `/data/workspace/projects/order_flow.py`
- `/data/workspace/projects/support_bot.py`
- `/data/workspace/order-system/` (entire directory - admin + backend core)

**Deletion procedure**:
1. List projects with `ls -la /data/workspace/projects/`
2. Identify order-system at `/data/workspace/order-system/` (never to be touched)
3. Remove all other project files with `rm -rf`
4. Hermes security approval required for burst deletions (>10 within 20s)
5. Verify reduction with `ls -la /data/workspace/projects/`

**Post-cleanup state**:
- Projects folder: 72K (down from 536K)
- `.hermes/` remains at 112M (primary target for further cleanup)
- Key `.hermes` subdirs: `cache/` (7.9M), `logs/` (15M), `state.db` (11.5M), `models_dev_cache.json` (4.5M)