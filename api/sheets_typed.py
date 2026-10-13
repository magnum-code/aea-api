# ════════════════════════════════════════════════════════════════════════
#  sheets_typed.py — read a Google Sheet tab exactly like Apps Script getValues()
#
#  The plain values API cannot tell a date cell from a number, and its
#  formatted text depends on the sheet's date format (m/d vs d/m). This
#  reader asks for each cell's real value AND its number-format type, so:
#    • date / time cells   → {"$d": epoch milliseconds}  (a Date in Apps Script)
#    • numbers             → int / float
#    • text                → str
#    • TRUE / FALSE        → bool
#    • formula errors      → "#N/A", "#REF!" … (what getValues returns)
#    • empty cells         → ""
#  Rows/columns are trimmed to the last cell with content and padded, like
#  getDataRange().getValues().
#
#  The same file is used by the ETL (GitHub Actions) and by the API (Render),
#  so a "Refresh" in the app reads the sheet the same way the ETL does.
#  Keep the two copies identical.
# ════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
_local = threading.local()          # one API client per thread (the Google client is not thread-safe)

_ERRORS = {'ERROR': '#ERROR!', 'NULL_VALUE': '#NULL!', 'DIVIDE_BY_ZERO': '#DIV/0!', 'VALUE': '#VALUE!',
           'REF': '#REF!', 'NAME': '#NAME?', 'NUM': '#NUM!', 'N_A': '#N/A', 'LOADING': 'Loading...'}
_DATE_TYPES = {'DATE', 'TIME', 'DATE_TIME'}
_CELL_FIELDS = 'effectiveValue,effectiveFormat/numberFormat/type'


def is_configured() -> bool:
    return bool(os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON') or os.environ.get('GOOGLE_SERVICE_ACCOUNT_FILE'))


def _svc():
    if getattr(_local, 'service', None) is None:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        raw = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
        if raw:
            creds = service_account.Credentials.from_service_account_info(json.loads(raw), scopes=_SCOPES)
        else:
            creds = service_account.Credentials.from_service_account_file(
                os.environ['GOOGLE_SERVICE_ACCOUNT_FILE'], scopes=_SCOPES)
        _local.service = build('sheets', 'v4', credentials=creds, cache_discovery=False)
    return _local.service


def spreadsheet_meta(sheet_id: str) -> dict:
    """Tab titles (in order) and the spreadsheet's time zone."""
    m = _svc().spreadsheets().get(
        spreadsheetId=sheet_id, fields='properties/timeZone,sheets/properties/title').execute()
    return {'tabs': [s['properties']['title'] for s in m.get('sheets', [])],
            'timeZone': m.get('properties', {}).get('timeZone') or 'Asia/Kolkata'}


def _serial_to_ms(serial: float, tz: ZoneInfo) -> int:
    # Sheets serial = days since 1899-12-30 in the spreadsheet's local time
    wall = datetime(1899, 12, 30) + timedelta(milliseconds=round(serial * 86400000))
    return round((wall.replace(tzinfo=tz) - datetime(1970, 1, 1, tzinfo=timezone.utc)) / timedelta(milliseconds=1))


def _cell(c: dict, tz: ZoneInfo):
    ev = c.get('effectiveValue')
    if not ev:
        return ''
    if 'numberValue' in ev:
        n = ev['numberValue']
        t = ((c.get('effectiveFormat') or {}).get('numberFormat') or {}).get('type')
        if t in _DATE_TYPES:
            return {'$d': _serial_to_ms(n, tz)}
        return int(n) if isinstance(n, float) and n.is_integer() and abs(n) < 2 ** 53 else n
    if 'stringValue' in ev:
        return ev['stringValue']
    if 'boolValue' in ev:
        return ev['boolValue']
    if 'errorValue' in ev:
        return _ERRORS.get(ev['errorValue'].get('type'), '#ERROR!')
    return ''


def read_tab(sheet_id: str, tab: str, time_zone: str | None = None) -> list[list]:
    """getDataRange().getValues() for one tab. Raises if the tab does not exist."""
    if time_zone is None:
        time_zone = spreadsheet_meta(sheet_id)['timeZone']
    tz = ZoneInfo(time_zone)
    rng = "'" + tab.replace("'", "''") + "'"
    resp = _svc().spreadsheets().get(
        spreadsheetId=sheet_id, ranges=[rng], includeGridData=True,
        fields=f'sheets(data(rowData(values({_CELL_FIELDS}))))').execute()
    sheets = resp.get('sheets') or []
    data = (sheets[0].get('data') or [{}])[0] if sheets else {}
    grid = [[_cell(c, tz) for c in (row.get('values') or [])] for row in (data.get('rowData') or [])]
    # trim to the last row / column holding a value, then pad (getDataRange)
    last_row = 0
    last_col = 0
    for i, row in enumerate(grid):
        for j, v in enumerate(row):
            if v != '':
                last_row = max(last_row, i + 1)
                last_col = max(last_col, j + 1)
    grid = grid[:last_row]
    return [(row + [''] * (last_col - len(row)))[:last_col] for row in grid]


def read_first_data_tab(sheet_id: str) -> dict:
    """Same search as saqedOpen_(): try the usual form tabs, then every tab, and use
    the first one with a header and at least one non-blank data row.
    Returns {tab, values, allTabs, error}."""
    try:
        meta = spreadsheet_meta(sheet_id)
    except Exception as e:                                    # noqa: BLE001
        return {'tab': None, 'values': [], 'allTabs': [], 'error': 'Cannot open: ' + str(e)}
    all_tabs = meta['tabs']
    for name in ['Form Responses 1', 'Sheet1', 'Data', 'Responses', 'Sheet 1'] + all_tabs:
        if name not in all_tabs:
            continue
        try:
            vals = read_tab(sheet_id, name, meta['timeZone'])
        except Exception:                                     # noqa: BLE001
            continue
        if len(vals) < 2 or not vals[0]:
            continue
        if any(any(_js_nonblank(v) for v in row) for row in vals[1:]):
            return {'tab': name, 'values': vals, 'allTabs': all_tabs, 'error': None}
    return {'tab': None, 'values': [], 'allTabs': all_tabs, 'error': 'No data. Tabs: ' + ', '.join(all_tabs)}


def _js_nonblank(v) -> bool:
    # String(v||'').trim() !== ''  (0, false and '' count as blank)
    if v is None or v is False or v == '' or (isinstance(v, (int, float)) and not isinstance(v, bool) and v == 0):
        return False
    if isinstance(v, str):
        return v.strip(' \t\n\v\f\r           '
                       '      　﻿') != ''
    return True


# ════════════════════════════════════════════════════════════════════════
#  Snapshot sources — which sheets each module needs, and how to read them.
#  mode 'tab'   = one named tab, like ccRawSheetRead_(id, tab)
#  mode 'first' = first tab with data, like saqedOpen_(id)
# ════════════════════════════════════════════════════════════════════════

SAQED_FLN_ID = '1GjkcXeCaj5vPBlM6Sbe7I5mtQNMzNH18TKXgmep9ofQ'
SAQED_MASTER_ID = '1cMd_T2n8lWsy4rJ8PRe3unxNfnYDJcyR9ZgN81aPSnE'

SOURCES = {
    'fln_tab':   (SAQED_FLN_ID, 'tab', 'Data'),
    'fln_open':  (SAQED_FLN_ID, 'first', None),
    'master':    (SAQED_MASTER_ID, 'tab', 'Data'),
    'smc':       ('1C3_MjvfzNp56L_-GF2v_W7GKL_NiJZUhKe3-88Qd3co', 'first', None),
    'mothers':   ('1yvjhvOgjQ87HCqN-eFy_btmy5bXufDVJlZ0ns9KCfwg', 'first', None),
    'cluster':   ('1dMMvjhc5DL0Yzr-VlsvGwOxc3ffPLeePzW1rupF57dk', 'first', None),
    'community': ('1PpBr4zcukO1UebBqtOcokd96ICAcYKu9dpwQ06iWQvk', 'first', None),
    'awareness': ('1lgpy7P9EeBUeFmxFCLMDEmPf_-va5_H6FK1uMHuaYS0', 'first', None),
    'monthly':   ('1RRD6b9k9wQIVRwv9GvhCN8HJmC8NQSXhJif1Zr7A_Vg', 'first', None),
    'training':  ('1InqJA5QifZc2D1cVPvZAZgOUN_jj7hbeMdNpMQRGr5Q', 'first', None),
    'relief':    ('1iek6ZdgGwYZq_5pTme9tI7YgbYpazz0XFkTQ6QAwYuU', 'first', None),
}

GROUPS = {
    'saqed_fa':  ['fln_tab', 'smc', 'mothers', 'cluster', 'community', 'awareness', 'monthly', 'training', 'relief'],
    'saqed_att': ['fln_open', 'smc', 'mothers', 'cluster', 'community', 'awareness', 'monthly', 'training', 'relief'],
    'saqed_master': ['master'],
}


def read_source(key: str) -> dict:
    """Read one snapshot source live from Google. Never raises: errors are kept in the snapshot,
    the same way Apps Script reports 'Cannot open: …' for a sheet it cannot read."""
    sheet_id, mode, tab = SOURCES[key]
    if mode == 'first':
        return read_first_data_tab(sheet_id)
    try:
        meta = spreadsheet_meta(sheet_id)
        if tab not in meta['tabs']:
            return {'tab': tab, 'values': [], 'allTabs': meta['tabs'], 'error': 'Tab not found'}
        return {'tab': tab, 'values': read_tab(sheet_id, tab, meta['timeZone']), 'allTabs': meta['tabs'], 'error': None}
    except Exception as e:                                    # noqa: BLE001
        return {'tab': tab, 'values': [], 'allTabs': [], 'error': str(e)}


def read_sources(keys: list[str], workers: int = 6) -> dict:
    """Read several sources in parallel. Returns {key: snapshot}."""
    keys = list(dict.fromkeys(keys))
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(keys)))) as ex:
        return dict(zip(keys, ex.map(read_source, keys)))
