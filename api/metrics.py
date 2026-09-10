# ════════════════════════════════════════════════════════════════════════
#  metrics.py
#
#  All metric computations that depend on runtime filters.
#  Exact port of Apps Script computeMisMetrics_, buildHeatmap_ etc.
#  These run on already-fetched rows from Supabase.
# ════════════════════════════════════════════════════════════════════════

from __future__ import annotations
import re
from datetime import date


# ── Helpers ──────────────────────────────────────────────────────────────

def _has_lang(r: dict) -> int:
    return (r["letter"] + r["word"] + r["sentence"] +
            r["paragraph"] + r["story"])


def _has_math(r: dict) -> int:
    return (r["number_sense"] + r["fmo"] + r["fractions"] +
            r["geometry"] + r["measurement"])


# ── computeMisMetrics_() ─────────────────────────────────────────────────

def compute_mis_metrics(rows: list[dict]) -> dict:
    total = single = combined = boys = girls = 0
    num_sense = fmo = fractions = geometry = measurement = 0
    letter = word = sentence = paragraph = story = 0
    teacher_set: set[str] = set()

    for r in rows:
        total += 1
        st = str(r.get("session_type") or "").strip().lower()
        if st == "single":   single   += 1
        if st == "combined": combined += 1

        boys  += r["boys"]
        girls += r["girls"]

        num_sense   += r["number_sense"]
        fmo         += r["fmo"]
        fractions   += r["fractions"]
        geometry    += r["geometry"]
        measurement += r["measurement"]
        letter      += r["letter"]
        word        += r["word"]
        sentence    += r["sentence"]
        paragraph   += r["paragraph"]
        story       += r["story"]

        t_cell = str(r.get("teacher_names") or "").strip()
        if t_cell:
            for t in re.split(r"[,;]", t_cell):
                nm = t.strip().lower()
                if nm:
                    teacher_set.add(nm)

    lang = letter + word + sentence + paragraph + story
    math = num_sense + fmo + fractions + geometry + measurement

    return {
        "total": total, "single": single, "combined": combined,
        "boys": boys, "girls": girls,
        "uniqueTeachers": len(teacher_set),
        "teachers":       len(teacher_set),
        "numSense": num_sense, "fmo": fmo, "fractions": fractions,
        "geometry": geometry, "measurement": measurement,
        "letter": letter, "word": word, "sentence": sentence,
        "paragraph": paragraph, "story": story,
        "langSessions": lang, "lang": lang,
        "mathSessions": math, "math": math,
        "langTopics": [letter, word, sentence, paragraph, story],
        "mathTopics":  [num_sense, fmo, fractions, geometry, measurement],
        "stem": 0,
    }


def count_stem(rows: list[dict]) -> int:
    return sum(1 for r in rows if r.get("stem_session") is True)


def build_heatmap(rows: list[dict]) -> list[dict]:
    hmap: dict[str, dict] = {}
    for r in rows:
        name   = str(r.get("name")   or "").strip()
        school = str(r.get("school") or "").strip()
        if not name or not school:
            continue
        key = f"{name}|||{school}"
        if key not in hmap:
            hmap[key] = {
                "name": name, "school": school, "sessions": 0,
                "numSense": 0, "fmo": 0, "fractions": 0,
                "geometry": 0, "measurement": 0,
                "letter": 0, "word": 0, "sentence": 0,
                "paragraph": 0, "story": 0,
            }
        e = hmap[key]
        e["sessions"]    += 1
        e["numSense"]    += r["number_sense"]
        e["fmo"]         += r["fmo"]
        e["fractions"]   += r["fractions"]
        e["geometry"]    += r["geometry"]
        e["measurement"] += r["measurement"]
        e["letter"]      += r["letter"]
        e["word"]        += r["word"]
        e["sentence"]    += r["sentence"]
        e["paragraph"]   += r["paragraph"]
        e["story"]       += r["story"]

    return sorted(hmap.values(), key=lambda x: (x["name"], x["school"]))


def compute_member_stats(rows: list[dict]) -> list[dict]:
    member_map: dict[str, dict] = {}
    for r in rows:
        name = str(r.get("name") or "").strip()
        if not name:
            continue
        if name not in member_map:
            member_map[name] = {"sessions": 0, "reach": 0, "lang": 0, "math": 0}
        m = member_map[name]
        m["sessions"] += 1
        m["reach"]    += r["boys"] + r["girls"]
        if _has_lang(r) > 0: m["lang"] += 1
        if _has_math(r) > 0: m["math"] += 1

    return sorted(
        [{"name": k, **v} for k, v in member_map.items()],
        key=lambda x: -x["sessions"]
    )


def compute_monthly_stats(rows: list[dict]) -> list[dict]:
    monthly_map: dict[str, dict] = {}
    for r in rows:
        raw_date = str(r.get("session_date") or "")
        ym = raw_date[:7]
        if len(ym) != 7 or ym[4] != "-":
            continue
        if ym not in monthly_map:
            monthly_map[ym] = {"month": ym, "sessions": 0, "reach": 0, "lang": 0, "math": 0}
        m = monthly_map[ym]
        m["sessions"] += 1
        m["reach"]    += r["boys"] + r["girls"]
        if _has_lang(r) > 0: m["lang"] += 1
        if _has_math(r) > 0: m["math"] += 1

    return sorted(monthly_map.values(), key=lambda x: x["month"])


def compute_school_stats(rows: list[dict]) -> list[dict]:
    school_map: dict[str, dict] = {}
    topic_keys = [
        ("numSense", "number_sense"), ("fmo", "fmo"),
        ("fractions", "fractions"),   ("geometry", "geometry"),
        ("measurement", "measurement"), ("letter", "letter"),
        ("word", "word"), ("sentence", "sentence"),
        ("paragraph", "paragraph"),   ("story", "story"),
    ]
    for r in rows:
        sc = str(r.get("school") or "").strip()
        if not sc:
            continue
        if sc not in school_map:
            school_map[sc] = {"name": sc, "sessions": 0, "reach": 0,
                              "lang": 0, "math": 0, "topics": {}}
        s = school_map[sc]
        s["sessions"] += 1
        s["reach"]    += r["boys"] + r["girls"]
        if _has_lang(r) > 0: s["lang"] += 1
        if _has_math(r) > 0: s["math"] += 1
        for out_key, in_key in topic_keys:
            val = r[in_key]
            if val > 0:
                s["topics"][out_key] = s["topics"].get(out_key, 0) + val

    return sorted(school_map.values(), key=lambda x: -x["sessions"])


# ── Attendance helpers ────────────────────────────────────────────────────

def count_days_in_range(start_date: str, end_date: str) -> int | None:
    """Matches countDaysInRange_() in Attendance.gs exactly."""
    if not start_date or not end_date:
        return None
    from datetime import date
    a = date.fromisoformat(start_date)
    b = date.fromisoformat(end_date)
    diff = (b - a).days
    return diff + 1 if diff >= 0 else None


def each_date_in_range(start_date: str, end_date: str) -> list[str]:
    """Matches eachDateInRange_() in Attendance.gs."""
    from datetime import date, timedelta
    dates = []
    a = date.fromisoformat(start_date)
    b = date.fromisoformat(end_date)
    cur = a
    while cur <= b:
        dates.append(str(cur))
        cur += timedelta(days=1)
    return dates
