# ════════════════════════════════════════════════════════════════════════
#  auth.py — who is calling, and are they allowed?
#
#  At sign-in the website (Vercel) gives the browser a signed token (JWT).
#  It carries the user's access levels per module, the same table Apps
#  Script's requireAccess() checks:  access = {ALGQE:{mis:'View',…}, SAQED:{fln:'View',…}}
#  The browser sends it as "Authorization: Bearer <token>". The API checks
#  the signature with JWT_SECRET (same value as on Vercel) and the level.
# ════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import os

import jwt
from fastapi import Header, HTTPException

_RANK = {'None': 0, 'View': 1, 'Edit': 2}
SESSION_EXPIRED = 'Your session has expired. Please sign in again.'


def _secret() -> str:
    s = os.environ.get('JWT_SECRET')
    if not s:
        raise HTTPException(500, 'JWT_SECRET is not set on the API server')
    return s


def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(401, SESSION_EXPIRED)
    token = authorization.split(' ', 1)[1].strip()
    try:
        return jwt.decode(token, _secret(), algorithms=['HS256'])
    except jwt.PyJWTError:
        raise HTTPException(401, SESSION_EXPIRED)


def has_access(user: dict, workspace: str, modules, level: str = 'View') -> bool:
    mods = modules if isinstance(modules, (list, tuple)) else [modules]
    acc = (user.get('access') or {}).get(workspace) or {}
    return any(_RANK.get(acc.get(m), 0) >= _RANK[level] for m in mods)


def require(user: dict, workspace: str, modules, level: str = 'View') -> None:
    """Same rule as requireAccess() in AccessControl.gs."""
    if not has_access(user, workspace, modules, level):
        raise HTTPException(403, 'Access denied')
