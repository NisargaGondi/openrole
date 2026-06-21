"""Dashboard stats."""

from fastapi import APIRouter

from openrole.db.repository import get_dashboard_stats
from openrole.scheduler.scout_log import last_scout_run

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard_stats():
    stats = get_dashboard_stats()
    last = last_scout_run()
    return {"stats": stats, "last_scout": last}
