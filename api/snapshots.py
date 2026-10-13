# ════════════════════════════════════════════════════════════════════════
#  snapshots.py — read the raw sheet copies from Supabase (with a memory
#  cache), and refresh them live from Google when asked.
#
#  Normal page load: uses the copies the ETL saved (fast).
#  Refresh button / stale approvals data: reads Google directly (needs
#  GOOGLE_SERVICE_ACCOUNT_JSON on Render), saves the new copy, then uses it.
# ════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from api import sheets_typed
from api.config import get_supabase

log = logging.getLogger(__name__)
_lock = threading.Lock()
_cache: dict[str, dict] = {}          # key → {'fetched_at': str, 'snap': {...}}


def _row_to_snap(r: dict) -> dict:
    return {'tab': r.get('tab'), 'values': r.get('values') or [], 'allTabs': r.get('all_tabs') or [],
            'error': r.get('error')}


def get(keys: list[str]) -> tuple[dict, dict]:
    """Return ({key: snapshot}, {key: fetched_at}) for the requested keys.
    Only re-downloads a copy when its fetched_at has changed."""
    sb = get_supabase()
    stamps = {r['key']: r['fetched_at'] for r in
              (sb.table('sheet_snapshots').select('key,fetched_at').in_('key', keys).execute().data or [])}
    with _lock:
        stale = [k for k in keys if k in stamps and _cache.get(k, {}).get('fetched_at') != stamps[k]]
    if stale:
        rows = sb.table('sheet_snapshots').select('*').in_('key', stale).execute().data or []
        with _lock:
            for r in rows:
                _cache[r['key']] = {'fetched_at': r['fetched_at'], 'snap': _row_to_snap(r)}
    with _lock:
        snaps = {k: _cache[k]['snap'] for k in keys if k in _cache and k in stamps}
    missing = [k for k in keys if k not in snaps]
    for k in missing:                     # never copied yet → same message Apps Script gives for an empty sheet
        snaps[k] = {'tab': None, 'values': [], 'allTabs': [], 'error': 'No data yet — the ETL has not copied this sheet'}
    return snaps, {k: stamps.get(k) for k in keys}


def age_minutes(fetched_at: str | None) -> float:
    if not fetched_at:
        return float('inf')
    t = datetime.fromisoformat(fetched_at.replace('Z', '+00:00'))
    return (datetime.now(timezone.utc) - t).total_seconds() / 60


def refresh(keys: list[str]) -> list[str]:
    """Read these sources live from Google and save them. Returns the keys refreshed.
    A sheet that fails to read keeps its previous copy."""
    if not sheets_typed.is_configured():
        log.warning('Live refresh skipped: GOOGLE_SERVICE_ACCOUNT_JSON is not set on the API server')
        return []
    fresh = sheets_typed.read_sources(keys)
    sb = get_supabase()
    old = {r['key']: r for r in (sb.table('sheet_snapshots').select('key,error,row_count')
                                 .in_('key', keys).execute().data or [])}
    now = datetime.now(timezone.utc).isoformat()
    done = []
    for k, s in fresh.items():
        o = old.get(k)
        if s.get('error') and o and not o.get('error') and (o.get('row_count') or 0) > 0:
            log.warning(f'Refresh of {k} failed, keeping previous copy: {s["error"]}')
            continue
        sb.table('sheet_snapshots').upsert({
            'key': k, 'sheet_id': sheets_typed.SOURCES[k][0], 'tab': s.get('tab'), 'all_tabs': s.get('allTabs') or [],
            'values': s.get('values') or [], 'error': s.get('error'),
            'row_count': max(len(s.get('values') or []) - 1, 0), 'source': 'live', 'fetched_at': now,
        }).execute()
        done.append(k)
    return done
