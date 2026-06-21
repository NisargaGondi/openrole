"""Activity log API."""

from fastapi import APIRouter

from openrole.api import activity_store

router = APIRouter(tags=["activity"])


@router.get("/activity")
def get_activity(limit: int = 60):
    return {"lines": activity_store.get_lines(limit)}


@router.delete("/activity")
def clear_activity():
    activity_store.clear()
    return {"cleared": True}
