import os
import threading
import time
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyCookie
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .planning import ProjectInput, Task, TaskID, plan
from .store import Store


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)


class Simulation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: TaskID
    hours: int = Field(ge=1, le=160, strict=True)
    version: int = Field(ge=1, strict=True)


class UserView(BaseModel):
    id: int
    email: str


class PlannedTask(Task):
    start: int
    finish: int
    slack: int
    critical: bool


class PlanView(BaseModel):
    duration: int
    effort: int
    critical_count: int
    tasks: list[PlannedTask]


class ProjectView(ProjectInput):
    id: str
    updated: int
    plan: PlanView


class SimulationView(BaseModel):
    baseline: int
    impact: int
    plan: PlanView
    version: int


class ErrorView(BaseModel):
    detail: str


def create_app(path=None, origin=None, secure=None, web_dir=None):
    store = Store(path or os.getenv("DB_PATH", "var/pathboard.sqlite"))
    app = FastAPI(
        title="Pathboard API",
        version="1.0.0",
        responses={422: {"model": ErrorView}},
        description="Dependency-aware project planning and critical-path simulation.",
    )
    app.state.store = store
    allowed_origin = origin or os.getenv("APP_ORIGIN", "http://localhost:8000")
    secure = secure if secure is not None else os.getenv("APP_ENV") == "production"
    attempts, lock = {}, threading.Lock()

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Validation output deliberately excludes submitted passwords and other inputs.
        messages = [f"{'.'.join(map(str, err['loc'][1:]))}: {err['msg']}" for err in exc.errors()]
        return JSONResponse({"detail": "; ".join(messages)}, status_code=422)

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("sec-fetch-site") == "cross-site" or request.headers.get(
                "origin"
            ) not in {None, allowed_origin}:
                return JSONResponse({"detail": "Origin not allowed."}, status_code=403)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 65536:
                    return JSONResponse(
                        {"detail": "Request is limited to 64 KiB."}, status_code=413
                    )
            request._body = bytes(body)
        if request.url.path.startswith("/api/auth/") and request.method == "POST":
            now, ip = time.monotonic(), request.client.host if request.client else "unknown"
            with lock:
                for key in list(attempts):
                    if attempts[key][1] < now:
                        del attempts[key]
                count, expires = attempts.get(ip, (0, now + 900))
                attempts[ip] = (count + 1, expires)
            if count >= 30:
                return JSONResponse(
                    {"detail": "Too many attempts. Try again later."},
                    status_code=429,
                    headers={"Retry-After": str(max(1, int(expires - now)))},
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    cookie_scheme = APIKeyCookie(name="session", auto_error=False)

    def current_user(token: Annotated[str | None, Depends(cookie_scheme)]):
        return store.user(token or "")

    User = Annotated[dict, Depends(current_user)]

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/auth/{action}", response_model=UserView)
    def auth(action: str, body: Credentials, response: Response):
        if action not in {"signup", "login"}:
            raise HTTPException(404, "Endpoint not found.")
        user, token = store.auth(body.email, body.password, action == "signup")
        response.set_cookie(
            "session", token, httponly=True, secure=secure, samesite="strict", max_age=86400
        )
        return user

    @app.get("/api/me", response_model=UserView)
    def me(user: User):
        return user

    @app.post("/api/logout")
    def logout(request: Request, response: Response, user: User):
        store.logout(request.cookies.get("session", ""))
        response.delete_cookie("session", httponly=True, secure=secure, samesite="strict")
        return {"ok": True}

    @app.get("/api/projects", response_model=list[ProjectView])
    def projects(user: User):
        return store.list(user["id"])

    @app.post("/api/projects", status_code=201, response_model=ProjectView)
    def create_project(body: ProjectInput, user: User):
        return store.save(user["id"], body)

    @app.get("/api/projects/{project_id}", response_model=ProjectView)
    def get_project(project_id: str, user: User):
        return store.get(user["id"], project_id)

    @app.put("/api/projects/{project_id}", response_model=ProjectView)
    def update_project(project_id: str, body: ProjectInput, user: User):
        return store.save(user["id"], body, project_id)

    @app.post("/api/projects/{project_id}/simulate", response_model=SimulationView)
    def simulate(project_id: str, body: Simulation, user: User):
        project = store.get(user["id"], project_id)
        if body.version != project["version"]:
            raise HTTPException(409, "Project changed. Reload before simulating.")
        document = ProjectInput.model_validate(
            {key: project[key] for key in ("name", "description", "tasks", "version")}
        )
        task = next((task for task in document.tasks if task.id == body.task_id), None)
        if not task:
            raise HTTPException(404, "Task not found.")
        task.hours = body.hours
        result = plan(document.tasks)
        return {
            "baseline": project["plan"]["duration"],
            "impact": result["duration"] - project["plan"]["duration"],
            "plan": result,
            "version": project["version"],
        }

    directory = Path(web_dir or os.getenv("WEB_DIR", "../web/dist"))
    if directory.exists():
        app.mount("/", StaticFiles(directory=directory, html=True), name="web")
    return app
