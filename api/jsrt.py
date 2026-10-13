# ════════════════════════════════════════════════════════════════════════
#  jsrt.py — JavaScript behaviour in Python
#
#  The Apps Script code relies on JavaScript rules for text, numbers and
#  dates (parseInt, parseFloat, String(), "truthy" values, Object key order,
#  localeCompare). Python behaves differently in small ways that change
#  totals and sort orders. Every ported module uses these helpers so the
#  results match Apps Script exactly.
#
#  Sheet values arrive from the snapshot in the same shape getValues() gives:
#  numbers, strings, booleans, '' for empty cells, and dates encoded as
#  {"$d": <milliseconds since 1970 UTC>} (see sheets_typed.py).
# ════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import math
import re
from decimal import Decimal


MONTHS = {'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
          'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'}
_MON_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
_DAY_ABBR = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

# Characters JavaScript's String.prototype.trim() removes
_JS_WS = ' \t\n\v\f\r             ' \
         '    　﻿'


MS_DAY = 86400000
IST_MIN = 330                                    # minutes east of UTC


def days_from_civil(y: int, m: int, d: int) -> int:
    """Days since 1970-01-01 for a proleptic Gregorian date (day may overflow the month)."""
    y2 = y - (1 if m <= 2 else 0)
    era = (y2 if y2 >= 0 else y2 - 399) // 400
    yoe = y2 - era * 400
    mp = (m + 9) % 12
    doy = (153 * mp + 2) // 5
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468 + (d - 1)


def civil_from_days(z: int):
    z += 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    return (y + (1 if m <= 2 else 0), m, d)


class JSDate:
    """A JavaScript Date. ms = milliseconds since epoch (NaN = Invalid Date)."""
    __slots__ = ('ms',)

    def __init__(self, ms: float):
        self.ms = float(ms) if ms is not None else math.nan

    def valid(self) -> bool:
        return not math.isnan(self.ms) and abs(self.ms) <= 8.64e15

    def parts(self, offset_min: int = IST_MIN):
        t = int(self.ms) + offset_min * 60000
        days = t // MS_DAY
        rem = t - days * MS_DAY
        y, m, d = civil_from_days(days)
        return {'y': y, 'm': m, 'd': d, 'H': rem // 3600000, 'M': (rem // 60000) % 60,
                'S': (rem // 1000) % 60, 'ms': rem % 1000, 'wd': (days + 4) % 7}   # wd: 0 = Sunday

    def iso(self) -> str:
        """Date.prototype.toISOString() / JSON.stringify(date)."""
        p = self.parts(0)
        y = p['y']
        ys = f'{y:04d}' if 0 <= y <= 9999 else (('+' if y > 0 else '-') + f'{abs(y):06d}')
        return f"{ys}-{p['m']:02d}-{p['d']:02d}T{p['H']:02d}:{p['M']:02d}:{p['S']:02d}.{p['ms']:03d}Z"

    def __repr__(self):
        return f'JSDate({self.iso() if self.valid() else "Invalid"})'


def decode_cell(v):
    if isinstance(v, dict) and '$d' in v:
        return JSDate(v['$d'])
    return v


def decode_grid(values):
    return [[decode_cell(c) for c in row] for row in (values or [])]


# ── truthiness / String() ────────────────────────────────────────────────

def truthy(v) -> bool:
    if v is None or v is False:
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return not (v == 0 or (isinstance(v, float) and math.isnan(v)))
    if isinstance(v, str):
        return v != ''
    return True                                   # objects, Dates (even invalid), arrays


def or_(v, default):
    """JavaScript `v || default`."""
    return v if truthy(v) else default


def num_str(x) -> str:
    if isinstance(x, bool):
        return 'true' if x else 'false'
    if isinstance(x, int):
        if abs(x) < 10 ** 21:
            return str(x)
        x = float(x)
    if math.isnan(x):
        return 'NaN'
    if math.isinf(x):
        return 'Infinity' if x > 0 else '-Infinity'
    if x == 0:
        return '0'
    if x.is_integer() and abs(x) < 1e21:
        return str(int(x))
    r = repr(x)
    if 'e' in r:
        mant, exp = r.split('e')
        e = int(exp)
        if -7 < e < 21:
            s = format(Decimal(r), 'f')
            if '.' in s:
                s = s.rstrip('0').rstrip('.')
            return s
        return f"{mant}e{'+' if e > 0 else '-'}{abs(e)}"
    return r


_DAY_SUN = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']


def _offset_at_utc_ms(ms: float) -> int:
    """Asia/Kolkata UTC offset (ms) at an instant, with historic offsets (as V8 uses)."""
    if not (-62135596800000 + 2 * MS_DAY < ms < 253402300799000 - 2 * MS_DAY):
        return IST_MIN * 60000
    from datetime import datetime, timezone as _tz
    from zoneinfo import ZoneInfo
    t = datetime.fromtimestamp(ms / 1000, _tz.utc).astimezone(ZoneInfo('Asia/Kolkata'))
    return int(t.utcoffset().total_seconds() * 1000)


def date_to_string(d: JSDate) -> str:
    """Date.prototype.toString() in the script time zone (Asia/Kolkata)."""
    if not d.valid():
        return 'Invalid Date'
    off = _offset_at_utc_ms(d.ms)
    t = int(d.ms) + off
    days = t // MS_DAY
    rem = t - days * MS_DAY
    y, m, dd = civil_from_days(days)
    om = abs(off) // 60000
    sign = '+' if off >= 0 else '-'
    return (f"{_DAY_SUN[(days + 4) % 7]} {_MON_ABBR[m - 1]} {dd:02d} {y:04d} "
            f"{rem // 3600000:02d}:{(rem // 60000) % 60:02d}:{(rem // 1000) % 60:02d} "
            f"GMT{sign}{om // 60:02d}{om % 60:02d} (India Standard Time)")


def js_str(v) -> str:
    """String(v)."""
    if v is None:
        return 'undefined'
    if isinstance(v, str):
        return v
    if isinstance(v, (bool, int, float)):
        return num_str(v)
    if isinstance(v, JSDate):
        return date_to_string(v)
    if isinstance(v, list):
        return ','.join('' if c is None else js_str(c) for c in v)
    return '[object Object]'


def trim(s: str) -> str:
    return s.strip(_JS_WS)


def trim_start(s: str) -> str:
    return s.lstrip(_JS_WS)


def lower(s: str) -> str:
    return s.lower()


# ── parseInt / parseFloat ────────────────────────────────────────────────

_FLOAT_RE = re.compile(r'[+-]?(?:Infinity|[0-9]+\.?[0-9]*(?:[eE][+-]?[0-9]+)?|\.[0-9]+(?:[eE][+-]?[0-9]+)?)')


def parse_float(v) -> float:
    s = trim_start(js_str(v))
    m = _FLOAT_RE.match(s)
    if not m:
        return math.nan
    t = m.group(0)
    if t.lstrip('+-') == 'Infinity':
        return -math.inf if t.startswith('-') else math.inf
    return float(t)


def parse_int(v) -> float:
    s = trim_start(js_str(v))
    sign = 1
    if s[:1] in '+-' and s[:1]:
        sign = -1 if s[0] == '-' else 1
        s = s[1:]
    radix = 10
    if s[:2].lower() == '0x':
        radix, s = 16, s[2:]
    digits = '0123456789abcdef'[:radix]
    n = 0
    k = 0
    for ch in s:
        dv = digits.find(ch.lower())
        if dv < 0:
            break
        n = n * radix + dv
        k += 1
    if k == 0:
        return math.nan
    return sign * n


def nz(x) -> float:
    """`x || 0` for a number that may be NaN."""
    return 0 if (isinstance(x, float) and math.isnan(x)) or x == 0 else x


# ── Dates ────────────────────────────────────────────────────────────────

def fmt(d: JSDate, pattern: str) -> str:
    """Utilities.formatDate(d, 'GMT+5:30', pattern) for the patterns the code uses."""
    if not d.valid():
        raise ValueError('Invalid argument: date')
    p = d.parts()
    if pattern == 'yyyy-MM-dd':
        return f"{p['y']:04d}-{p['m']:02d}-{p['d']:02d}"
    if pattern == 'dd MMM yyyy HH:mm':
        return f"{p['d']:02d} {_MON_ABBR[p['m'] - 1]} {p['y']:04d} {p['H']:02d}:{p['M']:02d}"
    raise ValueError('pattern ' + pattern)


def now() -> JSDate:
    import time
    return JSDate(round(time.time() * 1000))


_KOLKATA = None


def _local_offset_ms(y, local_ms):
    """Offset of Asia/Kolkata at a local wall time (historic offsets as in V8/ICU)."""
    global _KOLKATA
    if not (1 <= y <= 9998):
        return IST_MIN * 60000
    if _KOLKATA is None:
        from zoneinfo import ZoneInfo
        _KOLKATA = ZoneInfo('Asia/Kolkata')
    from datetime import datetime, timedelta
    wall = datetime(1970, 1, 1) + timedelta(milliseconds=local_ms)
    off = wall.replace(tzinfo=_KOLKATA).utcoffset()
    return int(off.total_seconds() * 1000)


def _ms(y, mo, d, h=0, mi=0, s=0, ms=0, offset_min=IST_MIN):
    """Wall-clock time at a fixed UTC offset → epoch ms (day may overflow the month, like V8)."""
    if not (1 <= mo <= 12) or not (1 <= d <= 31) or h > 24 or mi > 59 or s > 59:
        return None
    return (days_from_civil(y, mo, 1) + d - 1) * MS_DAY + ((h * 60 + mi) * 60 + s) * 1000 + ms - offset_min * 60000


# ── V8 date parser (port of v8/src/date/dateparser*.{h,cc}) ─────────────
_NONE = 2 ** 31 - 1
_KW = [  # (prefix, type, value)  — DateParser::KeywordTable
    ('jan', 'M', 1), ('feb', 'M', 2), ('mar', 'M', 3), ('apr', 'M', 4), ('may', 'M', 5), ('jun', 'M', 6),
    ('jul', 'M', 7), ('aug', 'M', 8), ('sep', 'M', 9), ('oct', 'M', 10), ('nov', 'M', 11), ('dec', 'M', 12),
    ('am', 'AMPM', 0), ('pm', 'AMPM', 12), ('ut', 'TZ', 0), ('utc', 'TZ', 0), ('z', 'TZ', 0), ('gmt', 'TZ', 0),
    ('cdt', 'TZ', -5), ('cst', 'TZ', -6), ('edt', 'TZ', -4), ('est', 'TZ', -5), ('mdt', 'TZ', -6),
    ('mst', 'TZ', -7), ('pdt', 'TZ', -7), ('pst', 'TZ', -8), ('t', 'TSEP', 0)]
_WS = set(_JS_WS) | {'\u180e'}


class _Tok:
    __slots__ = ('kind', 'num', 'len', 'sym', 'kwt', 'kwv')

    def __init__(self, kind, num=0, length=0, sym='', kwt=None, kwv=0):
        self.kind, self.num, self.len, self.sym, self.kwt, self.kwv = kind, num, length, sym, kwt, kwv

    def is_num(self): return self.kind == 'num'
    def is_sym(self, c): return self.kind == 'sym' and self.sym == c
    def is_sign(self): return self.kind == 'sym' and self.sym in '+-'
    def is_end(self): return self.kind == 'end'
    def is_ws(self): return self.kind == 'ws'
    def is_kw(self): return self.kind == 'kw'
    def is_fixed(self, n): return self.kind == 'num' and self.len == n
    def is_kw_z(self): return self.kind == 'kw' and self.kwt == 'TZ' and self.len == 1 and self.kwv == 0


class _Scanner:
    def __init__(self, s):
        self.s, self.i = s, 0
        self.nxt = self._scan()

    def _ch(self):
        return self.s[self.i] if self.i < len(self.s) else ''

    def _scan(self):
        s = self.s
        if self.i >= len(s):
            return _Tok('end')
        start, c = self.i, s[self.i]
        if '0' <= c <= '9':
            n = 0
            while self.i < len(s) and '0' <= s[self.i] <= '9':
                if n < _NONE // 10 - 10:
                    n = n * 10 + ord(s[self.i]) - 48
                self.i += 1
            return _Tok('num', n, self.i - start)
        if c in ':-+.)':
            self.i += 1
            return _Tok('sym', sym=c)
        if c >= 'A':
            pre = ''
            k = 0
            while self.i < len(s) and s[self.i] >= 'A' and s[self.i] not in _WS:
                if k < 3:
                    pre += chr(ord(s[self.i]) | 0x20)
                k += 1
                self.i += 1
            for kp, kt, kv in _KW:
                if pre[:3] == kp and (k <= 3 or kt == 'M') and (len(kp) == 3 or pre == kp):
                    return _Tok('kw', length=k, kwt=kt, kwv=kv)
            return _Tok('kw', length=k, kwt='INVALID')
        if c in _WS:
            while self.i < len(s) and s[self.i] in _WS:
                self.i += 1
            return _Tok('ws', length=self.i - start)
        if c == '(':
            bal = 0
            while True:
                ch = self._ch()
                if ch == ')':
                    bal -= 1
                elif ch == '(':
                    bal += 1
                self.i += 1
                if not (bal > 0 and self.i < len(s)):
                    break
            return _Tok('unknown')
        self.i += 1
        return _Tok('unknown')

    def next(self):
        t = self.nxt
        self.nxt = self._scan()
        return t

    def peek(self):
        return self.nxt

    def skip(self, c):
        if self.nxt.is_sym(c):
            self.next()
            return True
        return False


def _between(x, lo, hi): return lo <= x <= hi
def _is_month(x): return _between(x, 1, 12)
def _is_day(x): return _between(x, 1, 31)
def _is_hour(x): return _between(x, 0, 23)
def _is_min(x): return _between(x, 0, 59)
def _is_ms(x): return _between(x, 0, 999)


class _Day:
    def __init__(self): self.c, self.named, self.iso = [], None, False
    def empty(self): return not self.c
    def add(self, n):
        if len(self.c) < 3:
            self.c.append(n)
            return True
        return False

    def write(self):
        if not self.c:
            return None
        c = self.c + [1] * (3 - len(self.c))
        year = 0
        if self.named is None:
            if self.iso or not _is_day(c[0]):
                year, month, day = c[0], c[1], c[2]
            else:
                month, day, year = c[0], c[1], c[2]
        else:
            month = self.named
            if not _is_day(c[0]):
                year, day = c[0], c[1]
            else:
                day, year = c[0], c[1]
        if not self.iso:
            if _between(year, 0, 49):
                year += 2000
            elif _between(year, 50, 99):
                year += 1900
        if not _is_month(month) or not _is_day(day):
            return None
        return year, month, day


class _Time:
    def __init__(self): self.c, self.hour_off = [], None
    def empty(self): return not self.c
    def expecting(self, n):
        i = len(self.c)
        return (i == 1 and _is_min(n)) or (i == 2 and _is_min(n)) or (i == 3 and _is_ms(n))

    def add(self, n):
        if len(self.c) < 4:
            self.c.append(n)
            return True
        return False

    def add_final(self, n):
        if not self.add(n):
            return False
        self.c += [0] * (4 - len(self.c))
        return True

    def write(self):
        h, mi, s, ms = (self.c + [0] * 4)[:4]
        if self.hour_off is not None:
            if not _between(h, 0, 12):
                return None
            h = h % 12 + self.hour_off
        if not (_is_hour(h) and _is_min(mi) and _is_min(s) and _is_ms(ms)):
            if not (h == 24 and mi == 0 and s == 0 and ms == 0):
                return None
        return h, mi, s, ms


class _Tz:
    def __init__(self): self.sign, self.hour, self.minute = None, None, None
    def set(self, off):
        self.sign = -1 if off < 0 else 1
        self.hour, self.minute = off * self.sign, 0
    def expecting(self, n): return self.hour is not None and self.minute is None and _is_min(n)
    def is_utc(self): return self.hour == 0 and self.minute == 0
    def empty(self): return self.hour is None

    def write(self):
        if self.sign is None:
            return 'local'
        return self.sign * ((self.hour or 0) * 3600 + (self.minute or 0) * 60)


def _read_ms(t):
    n, ln = t.num, t.len
    if ln == 1:
        n *= 100
    elif ln == 2:
        n *= 10
    elif ln > 3:
        ln = min(ln, 9)
        while ln > 3:
            n //= 10
            ln -= 1
    return n


def _es5(sc, day, time, tz):
    if sc.peek().is_sign():
        sign_tok = sc.next()
        if not sc.peek().is_fixed(6):
            return sign_tok
        sign = -1 if sign_tok.sym == '-' else 1
        y = sc.next().num
        if sign < 0 and y == 0:
            return sign_tok
        day.add(sign * y)
    elif sc.peek().is_fixed(4):
        day.add(sc.next().num)
    else:
        return sc.next()
    if sc.skip('-'):
        if not sc.peek().is_fixed(2) or not _is_month(sc.peek().num):
            return sc.next()
        day.add(sc.next().num)
        if sc.skip('-'):
            if not sc.peek().is_fixed(2) or not _is_day(sc.peek().num):
                return sc.next()
            day.add(sc.next().num)
    if not (sc.peek().is_kw() and sc.peek().kwt == 'TSEP'):
        if not sc.peek().is_end():
            return sc.next()
    else:
        sc.next()
        if not sc.peek().is_fixed(2) or not _between(sc.peek().num, 0, 24):
            return _Tok('invalid')
        h24 = sc.peek().num == 24
        time.add(sc.next().num)
        if not sc.skip(':'):
            return _Tok('invalid')
        if not sc.peek().is_fixed(2) or not _is_min(sc.peek().num) or (h24 and sc.peek().num > 0):
            return _Tok('invalid')
        time.add(sc.next().num)
        if sc.skip(':'):
            if not sc.peek().is_fixed(2) or not _is_min(sc.peek().num) or (h24 and sc.peek().num > 0):
                return _Tok('invalid')
            time.add(sc.next().num)
            if sc.skip('.'):
                if not sc.peek().is_num() or (h24 and sc.peek().num > 0):
                    return _Tok('invalid')
                time.add(_read_ms(sc.next()))
        if sc.peek().is_kw_z():
            sc.next()
            tz.set(0)
        elif sc.peek().is_sym('+') or sc.peek().is_sym('-'):
            tz.sign = 1 if sc.next().sym == '+' else -1
            if sc.peek().is_fixed(4):
                hm = sc.next().num
                if not _is_hour(hm // 100) or not _is_min(hm % 100):
                    return _Tok('invalid')
                tz.hour, tz.minute = hm // 100, hm % 100
            else:
                if not sc.peek().is_fixed(2) or not _is_hour(sc.peek().num):
                    return _Tok('invalid')
                tz.hour = sc.next().num
                if not sc.skip(':'):
                    return _Tok('invalid')
                if not sc.peek().is_fixed(2) or not _is_min(sc.peek().num):
                    return _Tok('invalid')
                tz.minute = sc.next().num
        if not sc.peek().is_end():
            return _Tok('invalid')
    if tz.empty() and time.empty():
        tz.set(0)
    day.iso = True
    return _Tok('end')


def _nan():
    return JSDate(math.nan)


def date_parse(s: str) -> JSDate:
    """new Date(string) — a port of V8's DateParser (ES5 ISO form, then the legacy parser)."""
    sc = _Scanner(s)
    tz, time, day = _Tz(), _Time(), _Day()
    tok = _es5(sc, day, time, tz)
    if tok.kind == 'invalid':
        return _nan()
    has_num = not day.empty()
    while not tok.is_end():
        if tok.is_num():
            has_num = True
            n = tok.num
            if sc.skip(':'):
                if sc.skip(':'):
                    if not time.empty():
                        return _nan()
                    time.add(n)
                    time.add(0)
                else:
                    if not time.add(n):
                        return _nan()
                    if sc.peek().is_sym('.'):
                        sc.next()
            elif sc.skip('.') and time.expecting(n):
                time.add(n)
                if not sc.peek().is_num():
                    return _nan()
                time.add_final(_read_ms(sc.next()))
            elif tz.expecting(n):
                tz.minute = n
            elif time.expecting(n):
                time.add_final(n)
                pk = sc.peek()
                if not (pk.is_end() or pk.is_ws() or pk.is_kw_z() or pk.is_sign()):
                    return _nan()
            else:
                if not day.add(n):
                    return _nan()
                sc.skip('-')
        elif tok.is_kw():
            if tok.kwt == 'AMPM' and not time.empty():
                time.hour_off = tok.kwv
            elif tok.kwt == 'M':
                day.named = tok.kwv
                sc.skip('-')
            elif tok.kwt == 'TZ' and has_num:
                tz.set(tok.kwv)
            else:
                if has_num:
                    return _nan()
                if sc.peek().is_num():
                    return _nan()
        elif tok.is_sign() and (tz.is_utc() or not time.empty()):
            tz.sign = -1 if tok.sym == '-' else 1
            n, ln = 0, 0
            if sc.peek().is_num():
                t2 = sc.next()
                n, ln = t2.num, t2.len
            has_num = True
            if sc.peek().is_sym(':'):
                tz.hour, tz.minute = n, None
            elif ln in (1, 2):
                tz.hour, tz.minute = n, 0
            elif ln in (3, 4):
                tz.hour, tz.minute = n // 100, n % 100
            else:
                return _nan()
        elif (tok.is_sign() or tok.is_sym(')')) and has_num:
            return _nan()
        tok = sc.next()
    d = day.write()
    t = time.write()
    off = tz.write()
    if d is None or t is None:
        return _nan()
    y, mo, dd = d
    h, mi, sec, ms = t
    local = (days_from_civil(y, mo, 1) + dd - 1) * MS_DAY + ((h * 60 + mi) * 60 + sec) * 1000 + ms
    if off == 'local':
        utc = local - _local_offset_ms(y, local)
    else:
        utc = local - off * 1000
    if abs(utc) > 8.64e15:
        return _nan()
    return JSDate(utc)


def new_date(v) -> JSDate:
    """new Date(v)."""
    if isinstance(v, JSDate):
        return JSDate(v.ms)
    if isinstance(v, bool):
        return JSDate(1 if v else 0)
    if isinstance(v, (int, float)):
        return JSDate(v if not math.isinf(v) else math.nan)
    if v is None:
        return JSDate(math.nan)
    return date_parse(js_str(v))


# ── Object key order / sorting ───────────────────────────────────────────

def _is_index(k: str) -> bool:
    return k.isdigit() and k.isascii() and (k == '0' or k[0] != '0') and int(k) < 4294967295


def keys(d: dict) -> list:
    """Object.keys(d): integer-like keys ascending first, then insertion order."""
    idx = sorted((k for k in d if _is_index(k)), key=int)
    return idx + [k for k in d if not _is_index(k)]


def values(d: dict) -> list:
    return [d[k] for k in keys(d)]


def to_json_order(o):
    """Rebuild nested dicts in JavaScript key order and turn whole floats into ints,
    so the JSON sent to the browser is the same as JSON.stringify would produce."""
    if isinstance(o, dict):
        return {k: to_json_order(o[k]) for k in keys(o)}
    if isinstance(o, list):
        return [to_json_order(x) for x in o]
    if isinstance(o, float):
        if math.isnan(o) or math.isinf(o):
            return None
        if o.is_integer():
            return int(o)
    return o


def _collate_key(s: str):
    """Approximation of ICU root collation used by String.prototype.localeCompare:
    case and accents are ignored first; punctuation < digits < letters; then
    lowercase before uppercase."""
    import unicodedata
    prim, tert = [], []
    for ch in s:
        base = unicodedata.normalize('NFKD', ch)[0]
        if base.isalpha():
            prim.append((3, base.lower()))
            tert.append(0 if ch.islower() or not ch.isalpha() else 1)
        elif base.isdigit():
            prim.append((2, base))
            tert.append(0)
        elif base.isspace():
            prim.append((0, base))
            tert.append(0)
        else:
            prim.append((1, base))
            tert.append(0)
    return (prim, [unicodedata.normalize('NFKD', c) != c for c in s], tert)


def locale_compare(a: str, b: str) -> int:
    ka, kb = _collate_key(a), _collate_key(b)
    return (ka > kb) - (ka < kb)
