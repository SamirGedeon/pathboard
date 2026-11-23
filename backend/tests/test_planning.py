import pytest
from pydantic import ValidationError

from pathboard.planning import ProjectInput, Task, plan


def diamond():
    return [
        Task(id="a", title="Discover", hours=4),
        Task(id="b", title="Build", hours=6, dependencies=["a"]),
        Task(id="c", title="Write", hours=2, dependencies=["a"]),
        Task(id="d", title="Launch", hours=3, dependencies=["b", "c"]),
    ]


def test_diamond_known_critical_path_and_slack():
    p = plan(diamond())
    assert p["duration"] == 13
    assert p["effort"] == 15
    assert p["critical_count"] == 3
    assert {t["id"]: (t["start"], t["finish"], t["slack"]) for t in p["tasks"]} == {
        "a": (0, 4, 0),
        "b": (4, 10, 0),
        "c": (4, 6, 4),
        "d": (10, 13, 0),
    }


def test_parallel_branches_and_disconnected_task():
    tasks = diamond() + [Task(id="e", title="Independent", hours=8)]
    p = plan(tasks)
    assert p["duration"] == 13
    assert next(t for t in p["tasks"] if t["id"] == "e")["slack"] == 5


def test_equal_critical_branches_are_both_reported():
    tasks = diamond()
    tasks[2].hours = 6
    assert plan(tasks)["critical_count"] == 4


def test_estimate_change_uses_slack_before_extending_duration():
    tasks = diamond()
    tasks[2].hours = 5
    assert plan(tasks)["duration"] == 13
    tasks[2].hours = 7
    assert plan(tasks)["duration"] == 14


def test_empty_graph_and_stable_order():
    assert plan([]) == {"duration": 0, "effort": 0, "critical_count": 0, "tasks": []}
    assert plan(diamond()) == plan(list(reversed(diamond())))


@pytest.mark.parametrize(
    "tasks",
    [
        [{"id": "a", "title": "A", "hours": 1, "dependencies": ["a"]}],
        [{"id": "a", "title": "A", "hours": 1, "dependencies": ["missing"]}],
        [{"id": "a", "title": "A", "hours": 1}, {"id": "a", "title": "Duplicate", "hours": 2}],
        [
            {"id": "a", "title": "A", "hours": 1, "dependencies": ["b"]},
            {"id": "b", "title": "B", "hours": 1, "dependencies": ["a"]},
        ],
        [
            {"id": "a", "title": "A", "hours": 1},
            {"id": "b", "title": "B", "hours": 1, "dependencies": ["a", "a"]},
        ],
    ],
)
def test_invalid_dependency_graphs_rejected(tasks):
    with pytest.raises(ValidationError):
        ProjectInput(name="Example", tasks=tasks)


@pytest.mark.parametrize("hours", [0, 161, 1.5, True])
def test_estimates_are_bounded_integers(hours):
    with pytest.raises(ValidationError):
        Task(id="a", title="Task", hours=hours)
