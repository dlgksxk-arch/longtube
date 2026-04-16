"""Background task status router"""
from fastapi import APIRouter
from app.services.task_manager import get_task, cancel_task

router = APIRouter()


@router.get("/{project_id}/{step}")
async def get_task_status(project_id: str, step: str):
    """Get background task status for a given project + step"""
    state = get_task(project_id, step)
    if not state:
        return {"status": "idle", "step": step, "project_id": project_id}
    return state.to_dict()


@router.post("/{project_id}/{step}/cancel")
async def cancel_task_endpoint(project_id: str, step: str):
    """Cancel a running background task"""
    cancel_task(project_id, step)
    return {"status": "cancelled", "step": step}
