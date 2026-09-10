# ════════════════════════════════════════════════════════════════════════
#  routers/mis.py
#
#  MIS endpoints — exact equivalents of getDistrictDashboard(),
#  getAnalytics(), getDashboardConfig() in Mis.gs
#
#  GET /api/mis/dashboard?district=nalbari&start=2025-01-01&end=2025-12-31&name=All
# ════════════════════════════════════════════════════════════════════════

from __future__ import annotations
from fastapi import APIRouter, Query, HTTPException
from typing import Optional

from api.config import get_supabase, DISTRICTS
from api.metrics import (
    compute_mis_metrics, count_stem, build_heatmap,
    compute_member_stats, compute_monthly_stats, compute_school_stats,
)

router = APIRouter(prefix="/mis", tags=["MIS"])


def _fetch_mis_rows(district: str, start: str, end: str, name: str) -> list[dict]:
    """
    Fetch MIS rows from Supabase with filters applied.
    Matches loadSheetData_() + filter logic in getAnalytics() exactly.
    """
    sb = get_supabase()

    query = sb.table("mis_sessions").select("*").eq("district", district)

    if start:
        query = query.gte("session_date", start)
    if end:
        query = query.lte("session_date", end)
    if name and name != "All":
        query = query.eq("name", name)

    resp = query.limit(10000).execute()
    return resp.data or []


def _get_config(district: str) -> dict:
    """
    Returns member names and date range for filter dropdowns.
    Matches getDashboardConfig() in Mis.gs exactly.
    """
    sb = get_supabase()

    # Get distinct names
    names_resp = (
        sb.table("mis_sessions")
        .select("name")
        .eq("district", district)
        .execute()
    )
    names = sorted({r["name"] for r in (names_resp.data or []) if r.get("name")})

    # Get date range
    range_resp = (
        sb.table("mis_sessions")
        .select("session_date")
        .eq("district", district)
        .order("session_date", desc=False)
        .execute()
    )
    dates = [r["session_date"] for r in (range_resp.data or []) if r.get("session_date")]
    min_date = dates[0]  if dates else ""
    max_date = dates[-1] if dates else ""

    return {"names": names, "minDate": min_date, "maxDate": max_date}


@router.get("/dashboard")
def get_district_dashboard(
    district: str = Query(..., description="nalbari | baksa | dhemaji | lakhimpur"),
    start:    Optional[str] = Query(None, alias="start"),
    end:      Optional[str] = Query(None, alias="end"),
    name:     Optional[str] = Query("All"),
):
    """
    Combined config + analytics in one call.
    Matches getDistrictDashboard() in Mis.gs exactly.
    Returns identical JSON shape — frontend reads this as-is.
    """
    if district not in DISTRICTS:
        raise HTTPException(status_code=400, detail=f"Unknown district: {district}")

    try:
        config    = _get_config(district)
        analytics = _get_analytics(district, start or "", end or "", name or "All")
        return {"config": config, "analytics": analytics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics")
def get_analytics(
    district: str = Query(...),
    start:    Optional[str] = Query(None),
    end:      Optional[str] = Query(None),
    name:     Optional[str] = Query("All"),
):
    """
    Analytics only. Matches getAnalytics() in Mis.gs exactly.
    """
    if district not in DISTRICTS:
        raise HTTPException(status_code=400, detail=f"Unknown district: {district}")
    try:
        return _get_analytics(district, start or "", end or "", name or "All")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _get_analytics(district: str, start: str, end: str, name: str) -> dict:
    """
    Core analytics engine — matches getAnalytics() in Mis.gs exactly.
    All computation happens here on rows fetched from Supabase.
    """
    filtered  = _fetch_mis_rows(district, start, end, name)
    iclh_rows = [r for r in filtered if r.get("iclh") is True]

    all_metrics  = compute_mis_metrics(filtered)
    iclh_metrics = compute_mis_metrics(iclh_rows)
    iclh_metrics["stem"] = count_stem(iclh_rows)

    return {
        "success":      True,
        "totalRows":    len(filtered),
        "all":          all_metrics,
        "iclh":         iclh_metrics,
        "memberStats":  compute_member_stats(filtered),
        "monthlyStats": compute_monthly_stats(filtered),
        "schoolStats":  compute_school_stats(filtered),
        "heatAll":      {"rows": build_heatmap(filtered)},
        "heatICLH":     {"rows": build_heatmap(iclh_rows)},
    }


@router.get("/config")
def get_config(district: str = Query(...)):
    """
    Filter dropdown data only. Matches getDashboardConfig() in Mis.gs.
    """
    if district not in DISTRICTS:
        raise HTTPException(status_code=400, detail=f"Unknown district: {district}")
    try:
        return _get_config(district)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
