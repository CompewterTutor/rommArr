from decorators.auth import protected_route
from endpoints.responses import MessageResponse
from fastapi import Request
from handler.auth.constants import Scope
from tasks.update_launchbox_metadata import update_launchbox_metadata_task
from tasks.update_switch_titledb import update_switch_titledb_task
from utils.router import APIRouter

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
)


@protected_route(router.post, "/run", [Scope.TASKS_RUN])
async def run_tasks(request: Request) -> MessageResponse:
    """Run all tasks endpoint

    Args:
        request (Request): Fastapi Request object
    Returns:
        RunTasksResponse: Standard message response
    """

    await update_switch_titledb_task.run()
    await update_launchbox_metadata_task.run()
    return {"msg": "All tasks ran successfully!"}


@protected_route(router.post, "/{task}/run", [Scope.TASKS_RUN])
async def run_task(request: Request, task: str) -> MessageResponse:
    """Run single tasks endpoint

    Args:
        request (Request): Fastapi Request object
    Returns:
        RunTasksResponse: Standard message response
    """

    tasks = {
        "switch_titledb": update_switch_titledb_task,
        "launchbox_metadata": update_launchbox_metadata_task,
    }

    await tasks[task].run()
    return {"msg": f"Task {task} run successfully!"}
