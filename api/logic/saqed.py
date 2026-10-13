# ════════════════════════════════════════════════════════════════════════
#  logic/saqed.py — SAQED calculations, ported line by line from Saqed.gs
#
#  field_analytics()  ← getSaqedFieldAnalytics__impl_
#  master_data()      ← getSaqedMasterData__impl_
#  attendance()       ← getSaqedAttendance__impl_
#
#  Inputs are sheet snapshots (see snapshots.py). Each function returns the
#  same JSON object the Apps Script function returned, so the page code is
#  unchanged. JavaScript rules (parseInt, String(), key order …) come from
#  jsrt.py. Comments "JS:" quote the original line where it matters.
# ════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import re
import uuid
from functools import cmp_to_key

from api import jsrt as js
from api.jsrt import JSDate, truthy, or_, js_str, trim, lower

SAQED_MASTER_ID = '1cMd_T2n8lWsy4rJ8PRe3unxNfnYDJcyR9ZgN81aPSnE'
SAQED_MASTER_TAB = 'Data'
SAQED_FLN_ID = '1GjkcXeCaj5vPBlM6Sbe7I5mtQNMzNH18TKXgmep9ofQ'
SAQED_FLN_TAB = 'Data'

SAQED_FA_IDS = {
    'smc':       '1C3_MjvfzNp56L_-GF2v_W7GKL_NiJZUhKe3-88Qd3co',
    'mothers':   '1yvjhvOgjQ87HCqN-eFy_btmy5bXufDVJlZ0ns9KCfwg',
    'cluster':   '1dMMvjhc5DL0Yzr-VlsvGwOxc3ffPLeePzW1rupF57dk',
    'community': '1PpBr4zcukO1UebBqtOcokd96ICAcYKu9dpwQ06iWQvk',
    'awareness': '1lgpy7P9EeBUeFmxFCLMDEmPf_-va5_H6FK1uMHuaYS0',
    'monthly':   '1RRD6b9k9wQIVRwv9GvhCN8HJmC8NQSXhJif1Zr7A_Vg',
    'training':  '1InqJA5QifZc2D1cVPvZAZgOUN_jj7hbeMdNpMQRGr5Q',
    'relief':    '1iek6ZdgGwYZq_5pTme9tI7YgbYpazz0XFkTQ6QAwYuU',
}

SAQED_ROSTER = [
    "Abhinash Kardong", "Bebeto Pegu", "Bijeta Pegu", "Bineeta Pegu",
    "Biswajit Kumbang", "Rajkiran Pao", "Chandona Pao", "Devijyoti Kutum",
    "Dimbeswar Pegu", "Elina Kuli", "Gamuk Kutum", "Harakanta Taye", "Harikanta Tayeng",
    "Kabiraj Narah", "Julimoni Taye", "Indrajit Pegu", "Juratik Kutum",
    "Kamal Michong", "Kayum Pegu", "Krishna Ram Kardong", "Lakhyajyoti Handique", "Lilambar Pait",
    "Martina Regon", "Monika Doley", "Nilim Pegu", "Prasanta Doley", "Priyanka Doley",
    "Prokanta Padi", "Pushpadhar Boruah", "Rahim Doley", "Boloram Doley", "Ram Pegu",
    "Rashmi Rekha Das", "Ratul Doley", "Rimal Pegu", "Sanjib Doley", "Shantipriya Ngatey",
    "Shirumoni Pegu", "Sunmoni Bordoloi", "Tomash Pegu", "Tapan Pegu", "Tileswar Narah",
    "Bijoy Daimary", "Bwhwithi Narzary", "Montu Boro", "Punu Daimary", "Sondrika Narzary",
    "Satya Brata Gogoi", "Hemanta Dang", "Simran Rajbongshi",
]

# 250 SAQED programme schools (exact list from Saqed.gs, including its duplicates/typos)
SAQED_PROGRAMME_SCHOOLS = [
    "BORATI DIKHARI LPS", "LUHITPORIA LPS", "NO-2 LUHITPORIA LPS", "MUKTIAR KORAIBARI LPS", "MORA DIKHARI LPS",
    "BAHIR JONAI LPS", "BERA CHAPARI NOWGAON LPS", "TARI MAJ GAON LPS", "TARI BOSTI LPS", "BERA CHAPORI LPS",
    "JOYMAGURI LPS", "RAYANG KULI LPS", "KALAGURU BISHNU RAVA LPS", "RAYANG RATKEY LPS", "RATANPUR GOVT LPS",
    "AMLAKHIPAIT LPS", "AMLAKHI KUTUM LPS", "JAMING SANTIPUR LPS", "JANJI LPS", "MADHUPUR LP5",
    "KAMPUNG BURISUTI LPS", "JONAIMUKH KUTUM MVS", "GALI GHAT MACHKHUWA LPS", "NO-1 JIYADHAL LPS",
    "AMGURI KACHARI LPS", "NAHAR BANDANA LPS", "PADMACHUK SIRAMPURIA LPS", "NAHAR GEZERA LPS",
    "TARI BIJOYPUR GOVT LPS", "KARSANG BIJOYPUR LPS", "SONALI CHAPORI LPS", "UDAIPUR LPS", "BIBARI LPS",
    "DEKAPAM KUHIARBARI LPS", "TADUNIA LPS", "NEPALI BASTI LPS", "NO-3 NEPALI BOSTI LPS", "TORSING MILI LPS",
    "JONAI BAZAR GOVT LPS", "MIGOM DOLONG LPS", "SIMALUGURI JANAJATI LPS", "JELOM LPS", "ABOR LEKU LPS",
    "KEDI CHUBURI LPS", "NO-1 MURKOG SELEK LPS", "ARIMORA LPS", "AMRITPUR LPS", "MEDELA LPS",
    "ARIMARA CHAKAI A. KULI LPS", "RATANPUR PADI LPS", "NAHARANI LPS", "DEKAPAM CHARIALI LPS",
    "DEKA MAJGAON LPS", "ABOM NALA LPS", "PANITOLA MAJGAON LPS", "NO-2 KARDONGCHUK LPS",
    "UTTAR KARDONGCHUK LPS", "MAHMORA GOVT LPS", "AKLAND LPS", "SARANIA MAJ GAON LPS", "NAMONI BALI LPS",
    "MITE BORCAMP LPS", "RAYANG SANTIPUR LPS", "3 NO SUKAN NALA LPS", "RAYANG PATHAR MISHING LPS",
    "SIMEN CHAPORI LPS", "JODUMONI LPS", "SANKARDEV LPS", "MILAN BALI LPS", "NALAPARA LPS", "ANNAPUR LPS",
    "BORMURIA LPS", "MAGURMARI BODO LPS", "NO-2 BURIMURI BODO LPS", "NAWKATA BODO LPS", "BOIKUNTHAPUR LPS",
    "LAIMEKURI RESTCAMP LPS", "LAMPUNG MISHING LPS", "TAKO GITUNG GOVT LPS", "ADI TAKO LPS",
    "2NO MILANPUR LPS", "UDOIPUR DEPI CHAPORI LPS", "JOYPUR BODO LPS", "NO-2 KATHALGURI LPS",
    "RUKMINI KAYUM LPS", "RAKUT KEMERE LPS", "NO-3 LUHIJAN MAJGAON LPS", "AKLAND BOLAI LPS", "LUHIJAN LPS",
    "NO-2 BAHIRJONAI LPS", "NO-1 KAMAN SELEK LPS", "RAMDHAN GOVT LPS", "BURISUTI BONGALI LPS",
    "DIKHARI GOVT LPS", "JUNGAON LPS", "ATOKPUR LPS", "MILAN LPS", "DADHARA MADURI LPS", "BAGH GAON LPS",
    "KUMALIA LPS", "KER KER LPS", "HORIPUR DEORI LPS", "NO-2 BERA MAJ GAON LPS", "JWNG CHAR MILON LPS",
    "NALANI PAM LPS", "TELAM TOWN LPS", "GAMCHUK LPS", "TELAM LAKHIPUR LPS", "NO-2 KAMAN SELEK NEW LPS",
    "NO-2 TELAM NEPALI BOSTI LPS", "NAMONI ARUN CHAPORI LPS", "NO-2 KAMAN SELEK LPS", "LOKHI TINIALI LPS",
    "TELAM LPS", "SIMULUGURI MIKIR LPS", "LAMAJAN MAJGAON LPS", "SOMKONG NARAYANPUR LPS", "BOKAJAN LPS",
    "PUB ROWN LPS", "BRAHMAPUR BODO LPS", "CHENGAJAN KOIBATTA MVS", "LAMAJAN NILAKHIYA HEWJIA LPS",
    "KHERONI LPS", "JEAUTI LPS", "DULAKAKHARIA LPS", "JONEKARENG KACHARI LPS", "DEBING MISHING LPS",
    "SALARAM LPS", "JONEBOR LPS", "NAHAR JONE SUMAIMARI LPS", "SIGA BODOTI LPS", "SANTIPUR LPS",
    "SINGAPUR V LPS", "NO-2 LADANG GURI BODO LPS", "SIGA MISHING LPS", "PURONA JELEM LPS",
    "NO-2 PURANA JELEM LPS", "NO-2 M.SELEK RLY. COLONI LPS", "NO-2 M.SELEK FARM BOSTI LPS",
    "RAVA KATHONI MALBHUG LPS", "MADHYA BIJOYPUR LPS", "NO-5 UJANI BIJOYPUR LPS", "BIJOYPUR GOVT. LPS",
    "MADHYA NAMONI LPS", "MEMBER CHUK LPS", "BILPARA KANGKAN CHAPORI LPS", "LAMAJAN BIHIA LPS",
    "LAMAJAN JANAJATI LPS", "BILPAR NAVAJYOTI LPS", "BISGHARIA LPS", "KARICHUK LPS", "NO-3 MOHANPUR LPS",
    "HOSTINAPUR LPS", "MICHAMARA LPS", "MICHAMARA TINIALI LPS", "SHANTAPUR LPS", "SHANTIPUR GOVT LPS",
    "NO-2 SIKARI LPS", "BORBALI RANGAJAN LPS", "MAINAOPUR BODO LPS", "UDOIPUR KANGKAN CHAPORI LPS",
    "PALUNG LPS", "1NO MILON PUR LPS", "NO-1 UJANI MILANPUR LPS", "SIKARI GOVT LPS", "BORONG TELIJAN LPS",
    "BORONG BURISUTI LPS", "BORONG SARAI BARI LPS", "BORONG KRISHANAPUR LPS", "BORONG MADHYAPUR LPS",
    "MADHYA LAKHIPUR LPS", "NO-2 CHIRAMPURIA LPS", "AMGURI LPS", "BIJOYPUR BHEKELI LPS", "SIRAMPURIA LPS",
    "TARAJAN LPS", "LOKA PRIYA GUPINATH B. LPS", "JONAI TOWN LPS", "GINE MOHMORA LPS", "NO-2 MOHMORA LPS",
    "OYRAMGHAT LPS", "SIRUNG LPS", "KEMI GOVT. LPS", "SIRUNG LPS", "NO-1 ORIAMGHAT LPS",
    "NO-2 NAMKIR GAON LPS", "DEKAPAM LPS", "DEKAMISHING LPS", "BAHIR AMLAKHI PAIT LPS", "JAMJING LPS",
    "NO-2 BORONG K. PUR AHOM LPS", "NO-1 MUKALIPATHAR LPS", "KANKAN CHAPORI LPS", "BURIA CHAPORI MVS",
    "NO 2 KOILA ALI LPS", "TARI NEPALI BASTI LPS", "BAHIR CHILAI GOVT LPS", "NAHAR SILLEY LP5",
    "NO-2 RIGBI LPS", "RIGBI GOVT. LPS", "SOMKONG GOVT LPS", "LOKLUNG LPS", "PAGRO CHARAI BARI LPS",
    "SOMKONG MAJGAON LPS", "NAMONI PAGRO LPS", "JUNE KARENG REST CAMP LPS", "MOUZA CHAPORI LPS",
    "SONAPUR NAVAJYOTI LPS", "NO-1 SINGAPUR S.BORTY LPS", "NAHAR DETAK LPS", "LAMBA KANKAN MISHING LPS",
    "LOMBA MISHING LPS", "LAMBA CHAPORI LPS", "JOYPUR BAHBARI LPS", "NO-2 NAWKATA LPS",
    "NGABANG JANAJATI LPS", "BORBALI PUB RANKUP LPS", "MECHAKI GOVT LPS", "GALI GOVT LPS",
    "GALI MECHAKI MIGANG LPS", "AMAR BIJULI LPS", "NAHAR BIJULI LPS", "SIGA MAJGAON LPS",
    "SIGA BORGHULI LPS", "NO-2 NAHOR BORGULI LPS", "BALIGARAH BODO LPS", "SONAPUR BODO LPS",
    "LAKLUNG BODO LPS", "SOMKONG BODO LPS", "TADUNIA BODO LPS", "RAMPUR BIJAIPUR BODO LPS",
    "DEKAPAM BALABARI BODO LPS", "BOGORIGURI BODO MVS", "AGMA CHAPARI BODO LPS", "HOSONG BODO LPS",
    "BODALPUR BODO LPS", "NAMONI ULUONI BODO LPS", "PHAKHARIGURI LPS", "NO-1 BISHNUPUR LPS", "SIYALMARI LPS",
    "Maidangsri Rani Bodo LPS", "Silikaguri Bodo LPS", "Balabari Bodo LPS", "Hatijan Bodo LPS",
    "No-3 Sonapur Bodo LPS", "RVC Anjalu Bodo LPS", "Simen Chapori Bodo LPS", "Ulu Chapori Bodo LPS",
    "Majgaon Bodo LPS", "No 1 Burhabhakat Bodo LPS",
]


# ── Core helpers (same names as Saqed.gs) ────────────────────────────────

def saqed_open(snap: dict | None) -> dict:
    """saqedOpen_(): turn the chosen tab into row objects keyed by header."""
    if not snap:
        return {'rows': [], 'headers': [], 'allTabs': [], 'rowCount': 0, 'error': 'No snapshot'}
    if snap.get('error') or not snap.get('values'):
        return {'rows': [], 'headers': [], 'allTabs': snap.get('allTabs') or [], 'rowCount': 0,
                'error': snap.get('error') or 'No data. Tabs: ' + ', '.join(snap.get('allTabs') or [])}
    raw = js.decode_grid(snap['values'])
    headers = [trim(js_str(or_(h, ''))) for h in raw[0]]
    rows = []
    for r in raw[1:]:
        r = r + [''] * (len(headers) - len(r))
        if all(trim(js_str(or_(v, ''))) == '' for v in r):
            continue
        obj = {}
        for j, h in enumerate(headers):
            if h:
                obj[h] = r[j] if j < len(r) else None
        rows.append(obj)
    return {'rows': rows, 'headers': headers, 'allTabs': snap.get('allTabs') or [],
            'tabName': snap.get('tab'), 'rowCount': len(rows)}


def fc_(lh: list, headers: list, candidates: list):
    for cand in candidates:
        t = cand.lower()
        for j, h in enumerate(lh):
            if t in h:
                return headers[j]
    return None


def to_num(v) -> float:
    # JS: parseFloat(String(v||0).replace(/[^0-9.]/g,'')) || 0
    s = re.sub(r'[^0-9.]', '', js_str(or_(v, 0)))
    return js.nz(js.parse_float(s))


def to_str(v) -> str:
    return trim(js_str(or_(v, '')))


_LONG_DATE = re.compile(r'(?:[A-Za-z]{3}\s+)?([A-Za-z]{3})\s+([0-9]{1,2})\s+([0-9]{4})')


def to_date(v) -> str:
    """toDate_(): any timestamp value → 'yyyy-MM-dd' in IST."""
    if not truthy(v):
        return ''
    if isinstance(v, JSDate):
        return js.fmt(v, 'yyyy-MM-dd') if v.valid() else ''
    s = trim(js_str(v))
    if not s:
        return ''
    if re.match(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}', s):
        return s[:10]
    m = _LONG_DATE.search(s)
    if m:
        mon = js.MONTHS.get(m.group(1))
        if mon:
            return m.group(3) + '-' + mon + '-' + m.group(2).rjust(2, '0')
    d = js.date_parse(s)
    if d.valid():
        return js.fmt(d, 'yyyy-MM-dd')
    return s[:10]


def _get(row: dict, key):
    return row.get(key) if key else None


def _sort_desc(items: list, field: str) -> list:
    return sorted(items, key=lambda x: -x[field])


def _row(raw: list, i: int):
    """r[i] in JavaScript: undefined (None) when i is -1 or past the end."""
    return raw[i] if 0 <= i < len(raw) else None


# ════════════════════════════════════════════════════════════════════════
#  getSaqedFieldAnalytics
# ════════════════════════════════════════════════════════════════════════

def field_analytics(snaps: dict) -> dict:
    """snaps: {'fln_tab': snapshot of FLN 'Data', 'smc': …, 'mothers': …, … 'relief': …}"""
    result = {'success': True, 'fetchStatus': {}}

    # 1. FLN (On-site Support)
    try:
        fln_snap = snaps.get('fln_tab') or {}
        fln_raw = js.decode_grid(fln_snap.get('values'))
        if fln_raw and len(fln_raw) > 1:
            all_rows, cac_st, school_st = [], {}, {}
            subj = {'Literacy': 0, 'Numeracy': 0, 'Other': 0}
            for r in fln_raw[1:]:
                ts, staff, school, sub = _row(r, 0), to_str(_row(r, 1)), to_str(_row(r, 3)), to_str(_row(r, 5))
                boys = js.nz(js.parse_int(_row(r, 7)))
                girls = js.nz(js.parse_int(_row(r, 8)))
                tea = js.nz(js.parse_int(_row(r, 9)))
                c = cac_st.setdefault(staff, {'staff': staff, 'visits': 0, 'boys': 0, 'girls': 0, 'teachers': 0, 'schools': {}})
                c['visits'] += 1; c['boys'] += boys; c['girls'] += girls; c['teachers'] += tea
                if school:
                    c['schools'][school] = 1
                s = school_st.setdefault(school, {'name': school, 'visits': 0, 'students': 0, 'teachers': 0})
                s['visits'] += 1; s['students'] += boys + girls; s['teachers'] += tea
                sl = sub.lower()
                if 'lit' in sl:
                    subj['Literacy'] += 1
                elif 'num' in sl:
                    subj['Numeracy'] += 1
                else:
                    subj['Other'] += 1
                date_str = to_date(ts) if truthy(ts) else ''
                all_rows.append({'date': date_str, 'staff': staff, 'school': school, 'subject': sub,
                                 'boys': boys, 'girls': girls, 'teachers': tea})
            cac_arr = _sort_desc([{'staff': c['staff'], 'visits': c['visits'], 'boys': c['boys'], 'girls': c['girls'],
                                   'teachers': c['teachers'], 'uniqueSchools': len(c['schools'])}
                                  for c in js.values(cac_st)], 'visits')
            school_arr = _sort_desc(js.values(school_st), 'students')[:25]
            kpis = {'sessions': len(all_rows), 'boys': sum(r['boys'] for r in all_rows),
                    'girls': sum(r['girls'] for r in all_rows), 'teachers': sum(r['teachers'] for r in all_rows)}
            result['fln'] = {'kpis': kpis, 'cacStats': cac_arr, 'schoolStats': school_arr, 'subjectSplit': subj,
                             'rows': all_rows, 'totalProgrammeSchools': len(school_st)}
            result['fetchStatus']['fln'] = {'ok': True, 'rows': kpis['sessions']}
        else:
            result['fln'] = {}
            result['fetchStatus']['fln'] = {'ok': False, 'rows': 0}
    except Exception as e:                                         # noqa: BLE001
        result['fln'] = {}
        result['fetchStatus']['fln'] = {'ok': False, 'error': str(e)}

    # 2. SMC Meet
    try:
        d = saqed_open(snaps.get('smc'))
        if d['rowCount'] > 0:
            H = d['headers']; lh = [h.lower() for h in H]
            c_staff = fc_(lh, H, ['staff name', 'cac name', 'your name', 'name of cac', 'conducted by'])
            c_school = fc_(lh, H, ['school', 'venue', 'location', 'place'])
            c_date = fc_(lh, H, ['timestamp', 'date'])
            c_dur = fc_(lh, H, ['duration', 'time spent', 'how long', 'hours'])
            c_memb = fc_(lh, H, ['smc member', 'members attended', 'attendance', 'no. of member', 'number of member'])
            c_qt = fc_(lh, H, ['quarterly', 'quarterly training'])
            c_sdp = fc_(lh, H, ['sdp', 'school development plan', 'workshop'])
            staff_map, school_set, rows = {}, {}, []
            total_meets, total_members, total_qt, total_sdp = d['rowCount'], 0, 0, 0
            for r in d['rows']:
                staff = to_str(_get(r, c_staff)) if c_staff else ''
                school = to_str(_get(r, c_school)) if c_school else ''
                date = to_date(_get(r, c_date)) if c_date else ''
                dur = to_num(_get(r, c_dur)) if c_dur else 0
                memb = to_num(_get(r, c_memb)) if c_memb else 0
                qt = (1 if 'yes' in to_str(_get(r, c_qt)).lower() else to_num(_get(r, c_qt))) if c_qt else 0
                sdp = (1 if 'yes' in to_str(_get(r, c_sdp)).lower() else to_num(_get(r, c_sdp))) if c_sdp else 0
                total_members += memb; total_qt += qt; total_sdp += sdp
                if school:
                    school_set[school] = 1
                if staff:
                    s = staff_map.setdefault(staff, {'staff': staff, 'meets': 0, 'members': 0, 'lastDate': ''})
                    s['meets'] += 1; s['members'] += memb
                    if date and date > s['lastDate']:
                        s['lastDate'] = date
                rows.append({'date': date, 'staff': staff, 'school': school, 'duration': dur, 'members': memb})
            result['smc'] = {'totalMeets': total_meets, 'schoolsReached': len(school_set), 'totalMembers': total_members,
                             'totalQT': total_qt, 'totalSDP': total_sdp,
                             'byStaff': _sort_desc(js.values(staff_map), 'meets'), 'rows': rows}
            result['fetchStatus']['smc'] = {'ok': True, 'rows': total_meets}
        else:
            result['smc'] = {'error': d.get('error') or 'No data'}
            result['fetchStatus']['smc'] = {'ok': False, 'rows': 0, 'error': d.get('error')}
    except Exception as e:                                         # noqa: BLE001
        result['smc'] = {'error': str(e)}
        result['fetchStatus']['smc'] = {'ok': False, 'error': str(e)}

    # 3. Mothers Group
    try:
        d = saqed_open(snaps.get('mothers'))
        if d['rowCount'] > 0:
            H = d['headers']; lh = [h.lower() for h in H]
            c_staff = fc_(lh, H, ['staff name', 'cac name', 'your name', 'name of cac', 'conducted by'])
            c_school = fc_(lh, H, ['school', 'village', 'location', 'place'])
            c_date = fc_(lh, H, ['timestamp', 'date'])
            c_dur = fc_(lh, H, ['duration', 'time spent', 'how long', 'hours'])
            c_att = fc_(lh, H, ['attendance', 'mothers attended', 'no. of mother', 'number of mother', 'total mother'])
            c_active = fc_(lh, H, ['active', 'status', 'mg status'])
            staff_map, school_set, rows = {}, {}, []
            total_meets, total_att, active_mg, inactive_mg = d['rowCount'], 0, 0, 0
            for r in d['rows']:
                staff = to_str(_get(r, c_staff)) if c_staff else ''
                school = to_str(_get(r, c_school)) if c_school else ''
                date = to_date(_get(r, c_date)) if c_date else ''
                dur = to_num(_get(r, c_dur)) if c_dur else 0
                att = to_num(_get(r, c_att)) if c_att else 0
                active = to_str(_get(r, c_active)).lower() if c_active else ''
                total_att += att
                if 'active' in active and 'not' not in active:
                    active_mg += 1
                elif 'inactive' in active or 'not active' in active:
                    inactive_mg += 1
                if school:
                    school_set[school] = 1
                if staff:
                    s = staff_map.setdefault(staff, {'staff': staff, 'meets': 0, 'attendance': 0, 'lastDate': ''})
                    s['meets'] += 1; s['attendance'] += att
                    if date and date > s['lastDate']:
                        s['lastDate'] = date
                rows.append({'date': date, 'staff': staff, 'school': school, 'duration': dur, 'attendance': att})
            result['mothers'] = {'totalMeets': total_meets, 'schoolsReached': len(school_set), 'totalAttendance': total_att,
                                 'activeMG': active_mg, 'inactiveMG': inactive_mg,
                                 'byStaff': _sort_desc(js.values(staff_map), 'meets'), 'rows': rows}
            result['fetchStatus']['mothers'] = {'ok': True, 'rows': total_meets}
        else:
            result['mothers'] = {'error': d.get('error') or 'No data'}
            result['fetchStatus']['mothers'] = {'ok': False, 'rows': 0, 'error': d.get('error')}
    except Exception as e:                                         # noqa: BLE001
        result['mothers'] = {'error': str(e)}
        result['fetchStatus']['mothers'] = {'ok': False, 'error': str(e)}

    # 4. Cluster Teachers
    try:
        d = saqed_open(snaps.get('cluster'))
        if d['rowCount'] > 0:
            H = d['headers']; lh = [h.lower() for h in H]
            c_staff = fc_(lh, H, ['staff name', 'cac name', 'your name', 'conducted by'])
            c_school = fc_(lh, H, ['school', 'location', 'venue', 'place', 'cluster'])
            c_date = fc_(lh, H, ['timestamp', 'date'])
            c_dur = fc_(lh, H, ['duration', 'time spent', 'how long', 'hours'])
            c_att = fc_(lh, H, ['attendance', 'teachers attended', 'no. of teacher', 'number of teacher', 'total teacher'])
            c_topic = fc_(lh, H, ['topic', 'fln topic', 'subject discussed', 'topics discussed'])
            staff_map, school_set, topic_count, rows = {}, {}, {}, []
            total_meets, total_att = d['rowCount'], 0
            for r in d['rows']:
                staff = to_str(_get(r, c_staff)) if c_staff else ''
                school = to_str(_get(r, c_school)) if c_school else ''
                date = to_date(_get(r, c_date)) if c_date else ''
                dur = to_num(_get(r, c_dur)) if c_dur else 0
                att = to_num(_get(r, c_att)) if c_att else 0
                topic = to_str(_get(r, c_topic)) if c_topic else ''
                total_att += att
                if school:
                    school_set[school] = 1
                if topic:
                    topic_count[topic] = topic_count.get(topic, 0) + 1
                if staff:
                    s = staff_map.setdefault(staff, {'staff': staff, 'meets': 0, 'attendance': 0, 'lastDate': ''})
                    s['meets'] += 1; s['attendance'] += att
                    if date and date > s['lastDate']:
                        s['lastDate'] = date
                rows.append({'date': date, 'staff': staff, 'school': school, 'duration': dur, 'attendance': att, 'topic': topic})
            result['cluster'] = {'totalMeets': total_meets, 'schoolsReached': len(school_set), 'totalAttendance': total_att,
                                 'topicCount': len(topic_count), 'topics': topic_count,
                                 'byStaff': _sort_desc(js.values(staff_map), 'meets'), 'rows': rows}
            result['fetchStatus']['cluster'] = {'ok': True, 'rows': total_meets}
        else:
            result['cluster'] = {'error': d.get('error') or 'No data'}
            result['fetchStatus']['cluster'] = {'ok': False, 'rows': 0, 'error': d.get('error')}
    except Exception as e:                                         # noqa: BLE001
        result['cluster'] = {'error': str(e)}
        result['fetchStatus']['cluster'] = {'ok': False, 'error': str(e)}

    # 5. Community Event
    try:
        d = saqed_open(snaps.get('community'))
        if d['rowCount'] > 0:
            H = d['headers']; lh = [h.lower() for h in H]
            c_staff = fc_(lh, H, ['staff name', 'cac name', 'your name', 'conducted by'])
            c_school = fc_(lh, H, ['school', 'location', 'venue', 'place'])
            c_date = fc_(lh, H, ['timestamp', 'date'])
            c_dur = fc_(lh, H, ['duration', 'time spent', 'how long', 'hours'])
            c_att = fc_(lh, H, ['attendance', 'participants', 'attended', 'community members'])
            c_topic = fc_(lh, H, ['topic', 'subject', 'literacy', 'numeracy', 'type of topic', 'topic covered'])
            staff_map, school_set, rows = {}, {}, []
            total_events, total_att, lit_count, num_count = d['rowCount'], 0, 0, 0
            for r in d['rows']:
                staff = to_str(_get(r, c_staff)) if c_staff else ''
                school = to_str(_get(r, c_school)) if c_school else ''
                date = to_date(_get(r, c_date)) if c_date else ''
                dur = to_num(_get(r, c_dur)) if c_dur else 0
                att = to_num(_get(r, c_att)) if c_att else 0
                topic = to_str(_get(r, c_topic)).lower() if c_topic else ''
                total_att += att
                if 'lit' in topic:
                    lit_count += 1
                elif 'num' in topic:
                    num_count += 1
                if school:
                    school_set[school] = 1
                if staff:
                    s = staff_map.setdefault(staff, {'staff': staff, 'events': 0, 'attendance': 0, 'lastDate': ''})
                    s['events'] += 1; s['attendance'] += att
                    if date and date > s['lastDate']:
                        s['lastDate'] = date
                rows.append({'date': date, 'staff': staff, 'school': school, 'duration': dur, 'attendance': att, 'topic': topic})
            result['community'] = {'totalEvents': total_events, 'schoolsReached': len(school_set), 'totalAttendance': total_att,
                                   'literacyTopics': lit_count, 'numeracyTopics': num_count,
                                   'byStaff': _sort_desc(js.values(staff_map), 'events'), 'rows': rows}
            result['fetchStatus']['community'] = {'ok': True, 'rows': total_events}
        else:
            result['community'] = {'error': d.get('error') or 'No data'}
            result['fetchStatus']['community'] = {'ok': False, 'rows': 0, 'error': d.get('error')}
    except Exception as e:                                         # noqa: BLE001
        result['community'] = {'error': str(e)}
        result['fetchStatus']['community'] = {'ok': False, 'error': str(e)}

    # 6. Awareness Meet
    try:
        d = saqed_open(snaps.get('awareness'))
        if d['rowCount'] > 0:
            H = d['headers']; lh = [h.lower() for h in H]
            c_staff = fc_(lh, H, ['staff name', 'cac name', 'your name', 'conducted by'])
            c_school = fc_(lh, H, ['school', 'location', 'venue', 'place'])
            c_date = fc_(lh, H, ['timestamp', 'date'])
            c_dur = fc_(lh, H, ['duration', 'time spent', 'how long', 'hours'])
            c_att = fc_(lh, H, ['attendance', 'participants', 'attended', 'community', 'no. of people'])
            staff_map, school_set, rows = {}, {}, []
            total_meets, total_att = d['rowCount'], 0
            for r in d['rows']:
                staff = to_str(_get(r, c_staff)) if c_staff else ''
                school = to_str(_get(r, c_school)) if c_school else ''
                date = to_date(_get(r, c_date)) if c_date else ''
                dur = to_num(_get(r, c_dur)) if c_dur else 0
                att = to_num(_get(r, c_att)) if c_att else 0
                total_att += att
                if school:
                    school_set[school] = 1
                if staff:
                    s = staff_map.setdefault(staff, {'staff': staff, 'meets': 0, 'attendance': 0, 'lastDate': ''})
                    s['meets'] += 1; s['attendance'] += att
                    if date and date > s['lastDate']:
                        s['lastDate'] = date
                rows.append({'date': date, 'staff': staff, 'school': school, 'duration': dur, 'attendance': att})
            result['awareness'] = {'totalMeets': total_meets, 'schoolsReached': len(school_set), 'totalAttendance': total_att,
                                   'byStaff': _sort_desc(js.values(staff_map), 'meets'), 'rows': rows}
            result['fetchStatus']['awareness'] = {'ok': True, 'rows': total_meets}
        else:
            result['awareness'] = {'error': d.get('error') or 'No data'}
            result['fetchStatus']['awareness'] = {'ok': False, 'rows': 0, 'error': d.get('error')}
    except Exception as e:                                         # noqa: BLE001
        result['awareness'] = {'error': str(e)}
        result['fetchStatus']['awareness'] = {'ok': False, 'error': str(e)}

    # 7. Monthly Review / 8. Training — row counts only
    for key, field in (('monthly', 'totalMeetings'), ('training', 'totalEvents')):
        try:
            d = saqed_open(snaps.get(key))
            result[key] = {field: d['rowCount']}
            result['fetchStatus'][key] = {'ok': d['rowCount'] > 0, 'rows': d['rowCount'], 'error': d.get('error') or None}
        except Exception as e:                                     # noqa: BLE001
            result[key] = {field: 0}
            result['fetchStatus'][key] = {'ok': False, 'error': str(e)}

    # 9. Relief Camps
    try:
        d = saqed_open(snaps.get('relief'))
        if d['rowCount'] > 0:
            H = d['headers']; lh = [h.lower() for h in H]
            c_learn = fc_(lh, H, ['learning support', 'learning', 'educational support', 'study'])
            c_wash = fc_(lh, H, ['wash', 'water', 'sanitation', 'hygiene'])
            c_games = fc_(lh, H, ['indoor game', 'games', 'indoor', 'recreational'])
            tl = tw = tg = 0
            for r in d['rows']:
                ls = to_str(_get(r, c_learn)) if c_learn else ''
                ws = to_str(_get(r, c_wash)) if c_wash else ''
                gm = to_str(_get(r, c_games)) if c_games else ''
                if ls and ls.lower() != 'no':
                    tl += 1
                if ws and ws.lower() != 'no':
                    tw += 1
                if gm and gm.lower() != 'no':
                    tg += 1
            result['relief'] = {'totalVisits': d['rowCount'], 'learningSupportCount': tl, 'washCount': tw, 'indoorGamesCount': tg}
            result['fetchStatus']['relief'] = {'ok': True, 'rows': d['rowCount']}
        else:
            result['relief'] = {'totalVisits': 0, 'error': d.get('error') or 'No data'}
            result['fetchStatus']['relief'] = {'ok': False, 'rows': 0, 'error': d.get('error')}
    except Exception as e:                                         # noqa: BLE001
        result['relief'] = {'totalVisits': 0, 'error': str(e)}
        result['fetchStatus']['relief'] = {'ok': False, 'error': str(e)}

    return js.to_json_order(result)


# ════════════════════════════════════════════════════════════════════════
#  getSaqedMasterData — CAC attendance summary + conveyance claims
# ════════════════════════════════════════════════════════════════════════

def _master_date(raw_date) -> str:
    # From Apps Script's cache a date can arrive as ISO text; treated as the instant it names
    if isinstance(raw_date, str) and re.match(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}', raw_date):
        iso_d = js.new_date(raw_date)
        if iso_d.valid():
            raw_date = iso_d
    if isinstance(raw_date, JSDate):
        return js.fmt(raw_date, 'yyyy-MM-dd')          # Invalid Date throws, as in Apps Script
    s = trim(js_str(raw_date))
    if re.match(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}', s):
        return s[:10]
    parts = re.split(r'[/\-]', s.split(' ')[0])
    if len(parts) == 3:
        if len(parts[0]) == 4:
            return parts[0] + '-' + parts[1].rjust(2, '0') + '-' + parts[2].rjust(2, '0')
        return parts[2] + '-' + parts[1].rjust(2, '0') + '-' + parts[0].rjust(2, '0')    # DD/MM/YYYY
    return s[:10]


def master_data(snap: dict | None) -> dict:
    try:
        raw = js.decode_grid((snap or {}).get('values'))
        if not raw or len(raw) <= 1:
            return {'success': False, 'error': 'No Master data.'}
        headers = [trim(js_str(h)).lower() for h in raw[0]]

        def get_col(names):
            for n in names:
                for i, h in enumerate(headers):
                    if n in h:
                        return i
            return -1

        idx_time = get_col(['timestamp', 'date', 'time'])
        idx_staff = get_col(['staff name', 'cac name', 'name of staff', 'name'])
        idx_start = get_col(['starting place', 'start place', 'starting location', 'start location', 'from',
                             'starting point', 'hub', 'starting'])
        idx_session = get_col(['session type', 'type of session', 'activity', 'session'])
        idx_school = get_col(['school / location', 'school name', 'school / dest', 'school'])
        idx_success = get_col(['visit successful', 'successful'])
        idx_back = get_col(['travelling back', 'travel back', 'return', 'back'])
        idx_dist = get_col(['distance (km)', 'distance in km', 'distance'])
        idx_mode = get_col(['mode of transport', 'transport mode', 'mode'])
        idx_pub = get_col(['public transport cost', 'public cost', 'pub cost', 'public transport'])
        idx_amount = get_col(['total travel amount', 'travel amount', 'total amount', 'amount'])

        summary_map = {name: {'name': name, 'total': 0, 'daysSet': {}} for name in SAQED_ROSTER}
        detail, submitted_by_date, conv_map, all_dates = [], {}, {}, {}
        for r in raw[1:]:
            if not truthy(_row(r, idx_time)):
                continue
            date_str = _master_date(_row(r, idx_time))
            all_dates[date_str] = True
            staff = trim(js_str(or_(_row(r, idx_staff), '')))
            session = trim(js_str(or_(_row(r, idx_session), '')))
            school = trim(js_str(or_(_row(r, idx_school), '')))
            success = trim(js_str(or_(_row(r, idx_success), '')))
            detail.append({'date': date_str, 'staff': staff, 'session': session, 'school': school, 'success': success})
            sm = summary_map.setdefault(staff, {'name': staff, 'total': 0, 'daysSet': {}})
            sm['total'] += 1
            sm['daysSet'][date_str] = True
            submitted_by_date.setdefault(date_str, {})[staff] = True
            start_place = trim(js_str(or_(_row(r, idx_start), '')))
            travel_back = trim(js_str(or_(_row(r, idx_back), '')))
            dist = or_(_row(r, idx_dist), '0')
            if isinstance(dist, JSDate):          # JSON.stringify(Date) → ISO text
                dist = dist.iso() if dist.valid() else None
            mode = trim(js_str(or_(_row(r, idx_mode), '')))
            pub_cost = trim(js_str(or_(_row(r, idx_pub), ''))) or 'None Taken'
            amount = js.nz(js.parse_float(_row(r, idx_amount)))
            key = date_str + '|' + staff + '|' + school
            if key not in conv_map:
                conv_map[key] = {'id': str(uuid.uuid4()), 'date': date_str, 'staff': staff, 'startPlace': start_place,
                                 'school': school, 'sessions': [session], 'travelBack': travel_back, 'distance': dist,
                                 'mode': mode, 'pubCost': pub_cost, 'amount': amount, 'isApproved': False}
            else:
                conv_map[key]['sessions'].append(session)

        summary = sorted(({'name': k, 'total': summary_map[k]['total'],
                           'daysSubmitted': len(summary_map[k]['daysSet'])} for k in js.keys(summary_map)),
                         key=lambda x: -x['total'])
        missing = []
        for d_str in sorted(js.keys(all_dates), reverse=True):
            mc = [cac for cac in SAQED_ROSTER if not submitted_by_date.get(d_str, {}).get(cac)]
            if mc:
                missing.append({'date': d_str, 'missing': mc, 'count': len(mc)})
        conv = []
        for k in js.keys(conv_map):
            c = conv_map[k]
            c['sessions'] = ', '.join(c['sessions'])
            conv.append(c)

        def cmp(a, b):
            return js.locale_compare(b['date'], a['date']) or js.locale_compare(a['staff'], b['staff'])
        conv.sort(key=cmp_to_key(cmp))
        detail.reverse()
        return js.to_json_order({'success': True, 'attendance': {'summary': summary, 'detail': detail, 'missing': missing},
                                 'conveyance': conv})
    except Exception as e:                                         # noqa: BLE001
        return {'success': False, 'error': 'Error: ' + str(e)}


# ════════════════════════════════════════════════════════════════════════
#  getSaqedAttendance — CAC attendance across all SAQED forms
# ════════════════════════════════════════════════════════════════════════

ATT_SHEETS = [('fln_open', 'FLN Support'), ('smc', 'SMC Meet'), ('mothers', 'Mothers Group'),
              ('cluster', 'Cluster Teachers'), ('community', 'Community Event'), ('awareness', 'Awareness Meet'),
              ('monthly', 'Monthly Review'), ('training', 'Training/Refresher'), ('relief', 'Relief Camp')]


def attendance(snaps: dict, last_updated: JSDate | None = None) -> dict:
    try:
        submission_log, school_visit_log, all_dates = {}, {}, {}
        for key, label in ATT_SHEETS:
            try:
                d = saqed_open(snaps.get(key))
                if not d['rows']:
                    continue
                H = d['headers']; lh = [h.lower() for h in H]
                staff_key = fc_(lh, H, ['staff name', 'cac name', 'your name', 'name of cac', 'conducted by', 'name'])
                date_key = fc_(lh, H, ['timestamp', 'date', 'submission date'])
                school_key = fc_(lh, H, ['school name', 'name of the school', 'name of school', 'school'])
                if not staff_key or not date_key:
                    continue
                for row in d['rows']:
                    raw_date = row.get(date_key)
                    staff = to_str(row.get(staff_key))
                    if not truthy(raw_date) or not staff:
                        continue
                    date_str = to_date(raw_date if isinstance(raw_date, JSDate) else js.new_date(raw_date))
                    if not date_str or len(date_str) < 10:
                        continue
                    date_str = date_str[:10]
                    school = to_str(row.get(school_key)) if school_key else ''
                    all_dates[date_str] = True
                    mods = submission_log.setdefault(date_str, {}).setdefault(staff, [])
                    if label not in mods:
                        mods.append(label)
                    if school:
                        school_visit_log.setdefault(date_str, {})[school] = True
            except Exception:                                      # noqa: BLE001
                continue

        dates = sorted(js.keys(all_dates), reverse=True)
        cac = {n: {'name': n, 'daysActive': 0, 'totalSubmissions': 0, 'lastActive': ''} for n in SAQED_ROSTER}
        for date_str in js.keys(submission_log):
            for name in js.keys(submission_log[date_str]):
                c = cac.setdefault(name, {'name': name, 'daysActive': 0, 'totalSubmissions': 0, 'lastActive': ''})
                c['daysActive'] += 1
                c['totalSubmissions'] += len(submission_log[date_str][name])
                if not c['lastActive'] or date_str > c['lastActive']:
                    c['lastActive'] = date_str
        summary = [{'name': cac[n]['name'], 'daysActive': cac[n]['daysActive'],
                    'totalSubmissions': cac[n]['totalSubmissions'], 'lastActive': cac[n]['lastActive'] or 'Never',
                    'status': 'active' if cac[n]['totalSubmissions'] > 0 else 'inactive'} for n in SAQED_ROSTER]

        day_detail = []
        for date_str in dates:
            submitted = submission_log.get(date_str, {})
            names = sorted(js.keys(submitted))
            missing = [n for n in SAQED_ROSTER if not submitted.get(n)]
            visits = school_visit_log.get(date_str) or {}
            day_detail.append({
                'date': date_str, 'submitted': names, 'submittedCount': len(names),
                'missing': missing, 'missingCount': len(missing), 'totalRoster': len(SAQED_ROSTER),
                'schoolsVisited': sorted(js.keys(visits)),
                'schoolsNotVisited': [s for s in SAQED_PROGRAMME_SCHOOLS if not visits.get(s)],
                'entries': [{'cac': n, 'modules': submitted[n]} for n in js.keys(submitted)],
            })
        return js.to_json_order({
            'success': True, 'rosterCount': len(SAQED_ROSTER), 'daysTracked': len(dates),
            'summary': summary, 'dayDetail': day_detail,
            'missingReport': [d for d in day_detail if d['missingCount'] > 0],
            'allProgrammeSchools': SAQED_PROGRAMME_SCHOOLS,
            'lastUpdated': js.fmt(last_updated or js.now(), 'dd MMM yyyy HH:mm'),
        })
    except Exception as e:                                         # noqa: BLE001
        return {'success': False, 'error': str(e)}
