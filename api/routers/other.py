# ════════════════════════════════════════════════════════════════════════
#  routers/other.py
#
#  Route, Edu2025, Edu2026, SAQED endpoints.
#  All return pre-computed data from Supabase snapshot tables.
# ════════════════════════════════════════════════════════════════════════

from __future__ import annotations
import json
from fastapi import APIRouter, HTTPException

from api.config import get_supabase
from api.db import fetch_all, first_value

router = APIRouter(tags=["Other"])


# ── Route Planner ─────────────────────────────────────────────────────────

@router.get("/route/init")
def get_route_init():
    """
    Matches getRouteInit() in Route.gs.
    Returns ORS API key + all school locations.
    ORS key is now an env var — never exposed in source code.
    """
    import os
    ors_key = os.environ.get("ORS_API_KEY", "")
    sb = get_supabase()
    schools = fetch_all(lambda: sb.table("route_schools").select("*"))
    return {"orsApiKey": ors_key, "schools": schools}


# ── Edu 2025 ──────────────────────────────────────────────────────────────

@router.get("/edu2025/data")
def get_edu2025_data():
    """
    Matches get2025Data() in Edu2025.gs.
    Returns latest snapshot row from edu2025_summary.
    """
    try:
        sb   = get_supabase()
        resp = (sb.table("edu2025_summary")
                .select("*")
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute())
        rows = resp.data or []
        if not rows:
            return {"success": False, "error": "No Edu 2025 data available"}

        row = rows[0]
        # Parse JSONB fields back to dicts
        def j(field):
            v = row.get(field)
            if isinstance(v, str):
                return json.loads(v)
            return v or {}

        def ja(field):
            v = row.get(field)
            if isinstance(v, str):
                return json.loads(v)
            return v or []

        return {
            "success":       True,
            "totalStudents": row.get("total_students", 0),
            "totalSchools":  row.get("total_schools",  0),
            "boys":          row.get("boys",  0),
            "girls":         row.get("girls", 0),
            "cwsnTotal":     row.get("cwsn_total",   0),
            "cwsnMale":      row.get("cwsn_male",    0),
            "cwsnFemale":    row.get("cwsn_female",  0),
            "dropBoys":      row.get("drop_boys",    0),
            "dropGirls":     row.get("drop_girls",   0),
            "distStu":       j("dist_stu"),
            "distSch":       j("dist_sch"),
            "tongue":        j("tongue"),
            "category":      j("category"),
            "medium":        j("medium"),
            "classCount":    j("class_count"),
            "cluster":       j("cluster"),
            "schCat":        j("sch_cat"),
            "schoolPoints":  ja("school_points"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Edu 2026 ──────────────────────────────────────────────────────────────

@router.get("/edu2026/data")
def get_edu2026_data():
    """
    Matches getEdu2026Data() in Edu2026.gs.
    Returns latest snapshot from edu2026_summary.
    """
    try:
        sb   = get_supabase()
        resp = (sb.table("edu2026_summary")
                .select("*")
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute())
        rows = resp.data or []
        if not rows:
            return {"success": False, "error": "No Edu 2026 data available"}

        row = rows[0]

        def j(field):
            v = row.get(field)
            if isinstance(v, str):
                return json.loads(v)
            return v or {}

        students = j("students")
        schools  = j("schools")
        fln_cca  = j("fln_cca")
        fln_stem = j("fln_stem")

        return {
            "success":      True,
            "students":     students,
            "schools":      schools,
            "flnCca":       fln_cca,
            "flnStem":      fln_stem,
            "fetchStatus":  {
                "students": {"ok": True},
                "schools":  {"ok": True},
                "flnCca":   {"ok": True},
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# SAQED endpoints moved to routers/saqed.py (ported from the new Saqed.gs)
