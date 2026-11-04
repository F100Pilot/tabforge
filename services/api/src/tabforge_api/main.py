from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from tabforge_api.db import make_engine, make_session_factory
from tabforge_api.problems import ProblemError, install_problem_handlers
from tabforge_api.routes import jobs, tabs, uploads
from tabforge_api.settings import Settings
from tabforge_api.storage import ObjectStore, S3ObjectStore


def create_app(settings: Settings | None = None, store: ObjectStore | None = None) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]  # fields come from env
    app = FastAPI(title="TabForge API", version="0.1.0")
    engine = make_engine(settings.sqlalchemy_url)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.store = store or S3ObjectStore(settings)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["content-type"],
        )
    install_problem_handlers(app)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["ops"])
    def ready() -> dict[str, str]:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as exc:
            raise ProblemError(503, "database_unavailable", "database not reachable") from exc
        return {"status": "ready"}

    app.include_router(uploads.router)
    app.include_router(jobs.router)
    app.include_router(tabs.router)
    return app
