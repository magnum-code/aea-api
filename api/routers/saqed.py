# ════════════════════════════════════════════════════════════════════════
#  routers/saqed.py — SAQED endpoints (replace the Saqed.gs functions)
#
#  GET    /api/saqed/field-analytics[?force=1]  ← getSaqedFieldAnalytics(/Forced)  needs SAQED fln View
#  GET    /api/saqed/attendance[?force=1]       ← getSaqedAttendance(/Forced)      needs SAQED att View
#  GET    /api/saqed/master                     ← getSaqedMasterData               needs SAQED conv-app View
#  GET    /api/saqed/approved                   ← getApprovedConveyance            needs conv-pdf or conv-app View
#  POST   /api/saqed/approved                   ← saveApprovedConveyance           needs conv-app Edit
#  DELETE /api/saqed/approved                   ← clearApprovedConveyance          needs conv-app Edit
# ════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException

from api import jsrt as js
from api import snapshots
from api.auth import current_user, has_access, require
from api.config import get_supabase
from api.db import fetch_all
from api.logic import saqed as logic
from api.sheets_typed import GROUPS

router = APIRouter(prefix='/saqed', tags=['saqed'])

# Conveyance claims feed the approvals screen: read Google live when the copy is older than this.
MASTER_MAX_AGE_MIN = float(os.environ.get('SAQED_MASTER_MAX_AGE_MIN', '10'))
# Apps Script kept approved claims for 3 hours after the last save. 0 = keep until cleared.
APPROVED_TTL_HOURS = float(os.environ.get('SAQED_APPROVED_TTL_HOURS', '3'))

_memo: dict = {}
_memo_lock = threading.Lock()


def _computed(name: str, keys: list[str], fn):
    """Run a calculation once per set of sheet copies (results reused until the data changes)."""
    snaps, stamps = snapshots.get(keys)
    sig = (name, tuple(stamps.get(k) for k in keys))
    with _memo_lock:
        hit = _memo.get(name)
        if hit and hit[0] == sig:
            return hit[1]
    result = fn(snaps, stamps)
    with _memo_lock:
        _memo[name] = (sig, result)
    return result


def _latest(stamps: dict) -> js.JSDate:
    ts = [datetime.fromisoformat(v.replace('Z', '+00:00')) for v in stamps.values() if v]
    if not ts:
        return js.now()
    return js.JSDate(max(ts).timestamp() * 1000)


@router.get('/field-analytics')
def field_analytics(force: int = 0, user: dict = Depends(current_user)):
    require(user, 'SAQED', 'fln', 'View')
    keys = GROUPS['saqed_fa']
    if force:
        snapshots.refresh(keys)
    return _computed('fa', keys, lambda snaps, _: logic.field_analytics(snaps))


@router.get('/attendance')
def attendance(force: int = 0, user: dict = Depends(current_user)):
    require(user, 'SAQED', 'att', 'View')
    keys = GROUPS['saqed_att']
    if force:
        snapshots.refresh(keys)
    # lastUpdated = when the data was read from Google (Apps Script showed when it computed)
    return _computed('att', keys, lambda snaps, stamps: logic.attendance(snaps, _latest(stamps)))


@router.get('/master')
def master(user: dict = Depends(current_user)):
    require(user, 'SAQED', 'conv-app', 'View')
    keys = GROUPS['saqed_master']
    _, stamps = snapshots.get(keys)
    if snapshots.age_minutes(stamps.get('master')) > MASTER_MAX_AGE_MIN:
        snapshots.refresh(keys)
    # a new id for every claim on every call, as Apps Script did (Utilities.getUuid)
    snaps, _ = snapshots.get(keys)
    return logic.master_data(snaps['master'])


# ── Approved conveyance (was a 3-hour CacheService entry) ────────────────

_TOUCH_KEY = 'saqed_approved_touched'


def _approved_rows(sb) -> list[dict]:
    """Current approved list; empties it when it has expired, like the cache entry did."""
    if APPROVED_TTL_HOURS > 0:
        st = sb.table('app_state').select('updated_at').eq('key', _TOUCH_KEY).execute().data
        if st:
            touched = datetime.fromisoformat(st[0]['updated_at'].replace('Z', '+00:00'))
            if datetime.now(timezone.utc) - touched > timedelta(hours=APPROVED_TTL_HOURS):
                sb.table('saqed_approved_conveyance').delete().gte('id', 0).execute()
                sb.table('app_state').delete().eq('key', _TOUCH_KEY).execute()
                return []
        else:
            return []
    return fetch_all(lambda: sb.table('saqed_approved_conveyance').select('record'))


@router.get('/approved')
def get_approved(user: dict = Depends(current_user)):
    if not has_access(user, 'SAQED', ['conv-pdf', 'conv-app'], 'View'):
        return {'success': False, 'error': 'Access denied'}
    try:
        records = [r['record'] for r in _approved_rows(get_supabase())]
        return {'success': True, 'records': records, 'count': len(records),
                'ttlInfo': '~3 hours from last approval' if records else 'No approved records'}
    except Exception as e:                                         # noqa: BLE001
        return {'success': False, 'error': str(e)}


@router.post('/approved')
def save_approved(records: list = Body(default=None), user: dict = Depends(current_user)):
    if not has_access(user, 'SAQED', 'conv-app', 'Edit'):
        return {'success': False, 'error': 'Access denied'}
    try:
        if not records:
            return {'success': False, 'error': 'No records provided.'}
        sb = get_supabase()
        existing = [r['record'] for r in _approved_rows(sb)]
        seen = {(r or {}).get('_cid') or '' for r in existing}
        new = [r for r in records if isinstance(r, dict) and r.get('_cid') and r['_cid'] not in seen]
        approved_at = js.fmt(js.now(), 'dd MMM yyyy HH:mm')
        for r in new:
            r['approvedAt'] = approved_at
            r['approvedBy'] = 'Master Admin'
        if new:
            sb.table('saqed_approved_conveyance').insert(
                [{'cid': r['_cid'], 'record': r, 'approved_by': user.get('username') or user.get('user')} for r in new]
            ).execute()
        # saving restarts the 3-hour window, as cache.put did
        sb.table('app_state').upsert({'key': _TOUCH_KEY, 'value': None,
                                      'updated_at': datetime.now(timezone.utc).isoformat()}).execute()
        return {'success': True, 'savedCount': len(new), 'totalApproved': len(existing) + len(new),
                'expiresInHours': 3}
    except Exception as e:                                         # noqa: BLE001
        return {'success': False, 'error': str(e)}


@router.delete('/approved')
def clear_approved(user: dict = Depends(current_user)):
    if not has_access(user, 'SAQED', 'conv-app', 'Edit'):
        return {'success': False, 'error': 'Access denied'}
    try:
        sb = get_supabase()
        sb.table('saqed_approved_conveyance').delete().gte('id', 0).execute()
        sb.table('app_state').delete().eq('key', _TOUCH_KEY).execute()
        return {'success': True}
    except Exception as e:                                         # noqa: BLE001
        return {'success': False, 'error': str(e)}
