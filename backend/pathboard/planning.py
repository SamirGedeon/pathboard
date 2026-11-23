"""Deterministic critical-path planning for unlimited parallel resources."""

from heapq import heappop, heappush
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
TaskID = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,48}$")]


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: TaskID
    title: Title
    hours: int = Field(ge=1, le=160, strict=True)
    dependencies: list[TaskID] = Field(default_factory=list, max_length=60)


class ProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Title
    description: str = Field(default="", max_length=400)
    tasks: list[Task] = Field(default_factory=list, max_length=60)
    version: int = Field(default=0, ge=0, strict=True)

    @model_validator(mode="after")
    def valid_graph(self):
        plan(self.tasks)
        return self


def plan(tasks: list[Task]) -> dict:
    by_id = {task.id: task for task in tasks}
    if len(by_id) != len(tasks):
        raise ValueError("Task IDs must be unique.")
    children = {task.id: [] for task in tasks}
    indegree = {}
    for task in tasks:
        if len(set(task.dependencies)) != len(task.dependencies):
            raise ValueError("A dependency cannot appear twice.")
        indegree[task.id] = len(task.dependencies)
        for parent in task.dependencies:
            if parent not in by_id:
                raise ValueError("Every dependency must belong to this project.")
            if parent == task.id:
                raise ValueError("A task cannot depend on itself.")
            children[parent].append(task.id)
    ready = []
    for task_id, count in indegree.items():
        if count == 0:
            heappush(ready, task_id)
    order, starts, finishes = [], {}, {}
    while ready:
        task_id = heappop(ready)
        task = by_id[task_id]
        order.append(task_id)
        starts[task_id] = max((finishes[p] for p in task.dependencies), default=0)
        finishes[task_id] = starts[task_id] + task.hours
        for child in sorted(children[task_id]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heappush(ready, child)
    if len(order) != len(tasks):
        raise ValueError("Dependencies form a cycle. Remove a link to continue.")
    duration = max(finishes.values(), default=0)
    latest_start = {}
    for task_id in reversed(order):
        latest_finish = min((latest_start[c] for c in children[task_id]), default=duration)
        latest_start[task_id] = latest_finish - by_id[task_id].hours
    rows = [
        {
            **by_id[task_id].model_dump(),
            "start": starts[task_id],
            "finish": finishes[task_id],
            "slack": latest_start[task_id] - starts[task_id],
            "critical": latest_start[task_id] == starts[task_id],
        }
        for task_id in order
    ]
    return {
        "duration": duration,
        "effort": sum(task.hours for task in tasks),
        "critical_count": sum(row["critical"] for row in rows),
        "tasks": rows,
    }
