# ════════════════════════════════════════════════════════════════════════
#  routers/attendance.py
#
#  Attendance endpoints — matches getAttendanceInit(), getAttendanceData(),
#  getAttendanceConfig() in Attendance.gs exactly.
#
#  GET /api/attendance/init
#  GET /api/attendance/data?district=All&start=...&end=...&name=All
# ════════════════════════════════════════════════════════════════════════

from __future__ import annotations
import re
from datetime import date
from fastapi import APIRouter, Query, HTTPException
from typing import Optional

from api.config import get_supabase, DISTRICTS, DISTRICT_LABELS
from api.db import fetch_all, first_value
from api.metrics import count_days_in_range, each_date_in_range

router = APIRouter(prefix="/attendance", tags=["Attendance"])


def _fetch_att_rows(district: str, start: str, end: str, name: str) -> list[dict]:
    sb = get_supabase()

    def make():
        query = sb.table("attendance_submissions").select("*")
        if district and district != "All":
            query = query.eq("district", district)
        if start:
            query = query.gte("submission_date", start)
        if end:
            query = query.lte("submission_date", end)
        if name and name != "All":
            query = query.eq("name", name)
        return query

    return fetch_all(make)


def _fetch_all_rows_for_roster(districts: list[str]) -> list[dict]:
    """Fetch all rows (no date filter) for roster building."""
    sb = get_supabase()
    def make():
        query = sb.table("attendance_submissions").select("name,district,submission_date")
        if len(districts) < 4:
            query = query.in_("district", districts)
        return query
    return fetch_all(make)


def _get_config(districts: list[str]) -> dict:
    """Matches getAttendanceConfig() in Attendance.gs."""
    sb = get_supabase()

    names_rows = fetch_all(lambda: sb.table("attendance_submissions").select("name").in_("district", districts))
    names = sorted({r["name"] for r in names_rows if r.get("name")})

    dq = lambda: sb.table("attendance_submissions").select("submission_date").in_("district", districts)
    min_date = first_value(dq, "submission_date")
    max_date = first_value(dq, "submission_date", desc=True)

    return {
        "success":   True,
        "names":     names,
        "districts": [{"key": d, "label": DISTRICT_LABELS[d]} for d in DISTRICTS],
        "minDate":   min_date,
        "maxDate":   max_date,
    }


def _build_summary(filtered: list[dict], start: str, end: str) -> list[dict]:
    """
    Per-CEF summary. Matches cefMap logic in getAttendanceData() exactly.
    """
    cef_map: dict[str, dict] = {}

    for r in filtered:
        name     = r.get("name", "")
        district = r.get("district", "")
        if not name:
            continue
        key = f"{name}|||{district}"
        if key not in cef_map:
            cef_map[key] = {
                "name":             name,
                "district":         district,
                "districtLabel":    DISTRICT_LABELS.get(district, district),
                "cluster":          r.get("cluster", ""),
                "designation":      r.get("designation", ""),
                "email":            r.get("email", ""),
                "totalSubmissions": 0,
                "daysSubmitted":    {},
                "successfulCount":  0,
                "followupCount":    0,
            }
        c = cef_map[key]
        c["totalSubmissions"] += 1
        if r.get("submission_date"):
            c["daysSubmitted"][r["submission_date"]] = True
        if r.get("successful"):  c["successfulCount"] += 1
        if r.get("followup"):    c["followupCount"]   += 1
        # Keep latest non-empty cluster/designation
        if r.get("cluster"):     c["cluster"]     = r["cluster"]
        if r.get("designation"): c["designation"] = r["designation"]

    total_days = count_days_in_range(start, end)

    summary = []
    for c in cef_map.values():
        days_submitted = len(c["daysSubmitted"])
        summary.append({
            "name":             c["name"],
            "district":         c["district"],
            "districtLabel":    c["districtLabel"],
            "cluster":          c["cluster"],
            "designation":      c["designation"],
            "email":            c["email"],
            "totalSubmissions": c["totalSubmissions"],
            "daysSubmitted":    days_submitted,
            "daysMissed":       max(0, total_days - days_submitted) if total_days else None,
            "totalDaysInRange": total_days,
            "successfulCount":  c["successfulCount"],
            "followupCount":    c["followupCount"],
        })

    return sorted(summary, key=lambda x: (-x["totalSubmissions"], x["name"]))


def _build_detail(filtered: list[dict]) -> list[dict]:
    """Day-by-day detail rows. Matches detail logic in getAttendanceData()."""
    detail = []
    for r in filtered:
        district = r.get("district", "")
        detail.append({
            "date":          r.get("submission_date", ""),
            "name":          r.get("name", ""),
            "district":      district,
            "districtLabel": DISTRICT_LABELS.get(district, district),
            "cluster":       r.get("cluster", ""),
            "designation":   r.get("designation", ""),
            "session":       r.get("session", ""),
            "successful":    r.get("successful", False),
            "followup":      r.get("followup", False),
        })
    return sorted(detail, key=lambda x: (x["date"] or "", x["name"]), reverse=False)


def _build_missing(districts: list[str], start: str, end: str, name: str) -> dict:
    """
    Matches computeMissingSubmissions_() in Attendance.gs exactly.
    Builds roster from all historical rows, then finds missing per day.
    """
    if not start or not end:
        return {"days": [], "rosterSize": 0}

    # Build roster from all history (no date filter)
    all_rows = _fetch_all_rows_for_roster(districts)

    # roster: name|||district → firstSeenDate
    roster: dict[str, dict] = {}
    for r in all_rows:
        n = r.get("name", "")
        d = r.get("district", "")
        if not n:
            continue
        if name and name != "All" and n != name:
            continue
        key = f"{n}|||{d}"
        dt  = r.get("submission_date") or ""
        if key not in roster:
            roster[key] = {"name": n, "district": d,
                           "districtLabel": DISTRICT_LABELS.get(d, d),
                           "firstSeenDate": dt}
        elif dt and (not roster[key]["firstSeenDate"] or dt < roster[key]["firstSeenDate"]):
            roster[key]["firstSeenDate"] = dt

    roster_list = list(roster.values())

    # Who submitted per date (from filtered rows)
    sb = get_supabase()
    def make_sub():
        q = (sb.table("attendance_submissions")
             .select("name,district,submission_date")
             .in_("district", districts)
             .gte("submission_date", start)
             .lte("submission_date", end))
        if name and name != "All":
            q = q.eq("name", name)
        return q
    sub_rows = fetch_all(make_sub)

    submitted_by_date: dict[str, set] = {}
    for r in sub_rows:
        dt = r.get("submission_date")
        if not dt:
            continue
        if dt not in submitted_by_date:
            submitted_by_date[dt] = set()
        submitted_by_date[dt].add(f"{r['name']}|||{r['district']}")

    today_str = str(date.today())
    dates = [d for d in each_date_in_range(start, end) if d < today_str]

    days = []
    for dt in dates:
        submitted = submitted_by_date.get(dt, set())
        missing = [
            {"name": p["name"], "district": p["district"],
             "districtLabel": p["districtLabel"]}
            for p in roster_list
            if p["firstSeenDate"] and p["firstSeenDate"] <= dt
            and f"{p['name']}|||{p['district']}" not in submitted
        ]
        missing.sort(key=lambda x: x["name"])
        days.append({"date": dt, "missing": missing, "missingCount": len(missing)})

    return {"days": days, "rosterSize": len(roster_list)}


@router.get("/init")
def get_attendance_init():
    """
    Combined config + data. Matches getAttendanceInit() in Attendance.gs.
    Called once on module open.
    """
    try:
        config = _get_config(DISTRICTS)
        data   = _get_attendance_data(
            "All", config["minDate"], config["maxDate"], "All"
        )
        return {"config": config, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data")
def get_attendance_data(
    district: Optional[str] = Query("All"),
    start:    Optional[str] = Query(None),
    end:      Optional[str] = Query(None),
    name:     Optional[str] = Query("All"),
):
    """
    Matches getAttendanceData() in Attendance.gs exactly.
    """
    try:
        return _get_attendance_data(
            district or "All", start or "", end or "", name or "All"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _get_attendance_data(district: str, start: str, end: str, name: str) -> dict:
    districts = (
        [district] if district and district != "All" else DISTRICTS
    )

    filtered = _fetch_att_rows(district, start, end, name)
    summary  = _build_summary(filtered, start, end)
    detail   = _build_detail(filtered)

    try:
        missing = _build_missing(districts, start, end, name)
    except Exception as e:
        missing = {"days": [], "rosterSize": 0, "error": str(e)}

    return {
        "success":       True,
        "totalRows":     len(filtered),
        "summary":       summary,
        "detail":        detail,
        "missingByDay":  missing["days"],
        "rosterSize":    missing["rosterSize"],
        "districtErrors": [],
    }
