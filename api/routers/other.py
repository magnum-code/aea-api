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
    resp = sb.table("route_schools").select("*").execute()
    schools = resp.data or []
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


# ── SAQED ─────────────────────────────────────────────────────────────────

@router.get("/saqed/analytics")
def get_saqed_analytics():
    """
    Matches getSaqedFieldAnalytics() in Saqed.gs.
    Returns latest FA snapshot + computed FLN stats.
    """
    try:
        sb = get_supabase()

        # Latest FA cache snapshot
        fa_resp = (sb.table("saqed_fa_cache")
                   .select("*")
                   .order("snapshot_date", desc=True)
                   .limit(1)
                   .execute())
        fa_rows = fa_resp.data or []

        def j(field, row):
            v = row.get(field)
            if isinstance(v, str):
                return json.loads(v)
            return v or {}

        fa = {}
        fetch_status = {}
        if fa_rows:
            row = fa_rows[0]
            for module in ["smc", "mothers", "cluster", "community",
                           "awareness", "monthly", "training", "relief"]:
                fa[module] = j(module, row)
            fetch_status = j("fetch_status", row)

        # FLN rows — all of them so client can filter
        fln_resp = sb.table("saqed_fln_rows").select("*").execute()
        fln_rows = fln_resp.data or []

        # Build FLN aggregates (matches getSaqedFieldAnalytics fln section)
        cac_st:    dict[str, dict] = {}
        school_st: dict[str, dict] = {}
        subj = {"Literacy": 0, "Numeracy": 0, "Other": 0}
        all_rows = []

        for r in fln_rows:
            staff  = r.get("staff", "")
            school = r.get("school", "")
            boys   = r.get("boys", 0)
            girls  = r.get("girls", 0)
            tea    = r.get("teachers", 0)
            cat    = r.get("subject_cat", "Other")
            dt     = r.get("visit_date", "")

            if staff not in cac_st:
                cac_st[staff] = {"staff": staff, "visits": 0, "boys": 0,
                                 "girls": 0, "teachers": 0, "schools": set()}
            cac_st[staff]["visits"]   += 1
            cac_st[staff]["boys"]     += boys
            cac_st[staff]["girls"]    += girls
            cac_st[staff]["teachers"] += tea
            if school:
                cac_st[staff]["schools"].add(school)

            if school not in school_st:
                school_st[school] = {"name": school, "visits": 0,
                                     "students": 0, "teachers": 0}
            school_st[school]["visits"]   += 1
            school_st[school]["students"] += boys + girls
            school_st[school]["teachers"] += tea

            subj[cat] = subj.get(cat, 0) + 1
            all_rows.append({
                "date": str(dt) if dt else "",
                "staff": staff, "school": school,
                "subject": r.get("subject", ""),
                "boys": boys, "girls": girls, "teachers": tea,
            })

        cac_arr = sorted(
            [{"staff": k, "visits": v["visits"], "boys": v["boys"],
              "girls": v["girls"], "teachers": v["teachers"],
              "uniqueSchools": len(v["schools"])}
             for k, v in cac_st.items()],
            key=lambda x: -x["visits"]
        )
        school_arr = sorted(school_st.values(),
                            key=lambda x: -x["students"])[:25]

        kpis = {
            "sessions": len(all_rows),
            "boys":     sum(r["boys"]     for r in all_rows),
            "girls":    sum(r["girls"]    for r in all_rows),
            "teachers": sum(r["teachers"] for r in all_rows),
        }

        return {
            "success": True,
            "fln": {
                "kpis":                kpis,
                "cacStats":            cac_arr,
                "schoolStats":         school_arr,
                "subjectSplit":        subj,
                "rows":                all_rows,
                "totalProgrammeSchools": len(school_st),
            },
            **fa,
            "fetchStatus": fetch_status,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/saqed/master")
def get_saqed_master():
    """Returns SAQED master data."""
    try:
        sb   = get_supabase()
        resp = sb.table("saqed_fln_rows").select("*").execute()
        return {"success": True, "rows": resp.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
