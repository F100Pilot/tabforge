from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text

from tabforge_api.auth import CSRF_HEADER
from tabforge_api.db import make_engine, make_session_factory
from tabforge_api.limits import SlidingWindowLimiter
from tabforge_api.local_storage import LocalObjectStore
from tabforge_api.mailer import Mailer, build_mailer
from tabforge_api.problems import ProblemError, install_problem_handlers
from tabforge_api.routes import (
    auth,
    imports,
    jobs,
    local_storage,
    me,
    references,
    tabs,
    tuning,
    uploads,
)
from tabforge_api.settings import LOOPBACK_HOSTS, Settings
from tabforge_api.storage import ObjectStore, S3ObjectStore


def create_app(
    settings: Settings | None = None,
    store: ObjectStore | None = None,
    mailer: Mailer | None = None,
) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]  # fields come from env
    mailer = mailer or build_mailer(settings)  # fails closed outside dev without SMTP
    local = settings.storage_backend == "local"
    if local:
        store = store or LocalObjectStore.from_settings(settings)
        if not isinstance(store, LocalObjectStore):  # the upload route writes through it
            raise ValueError("storage_backend=local needs a LocalObjectStore")
    app = FastAPI(title="TabForge API", version="0.1.0")
    engine = make_engine(settings.sqlalchemy_url)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.store = store or S3ObjectStore(settings)
    app.state.mailer = mailer
    app.state.write_limiter = SlidingWindowLimiter(settings.write_rate_per_minute, 60)
    app.state.magic_link_email_limiter = SlidingWindowLimiter(
        auth.MAGIC_LINK_PER_EMAIL, auth.MAGIC_LINK_WINDOW_S
    )
    app.state.magic_link_ip_limiter = SlidingWindowLimiter(
        auth.MAGIC_LINK_PER_IP, auth.MAGIC_LINK_WINDOW_S
    )
    app.state.desktop_login_limiter = SlidingWindowLimiter(
        auth.DESKTOP_LOGIN_PER_IP, auth.DESKTOP_LOGIN_WINDOW_S
    )

    if settings.cors_origins:
        if "*" in settings.cors_origins:  # credentialed CORS needs explicit origins
            raise ValueError("TABFORGE_CORS_ORIGINS must list explicit origins, not '*'")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            # PUT only for the local signed upload; with S3 the browser PUTs to the bucket.
            allow_methods=["GET", "POST", "DELETE", *(["PUT"] if local else [])],
            allow_headers=["Content-Type", CSRF_HEADER],
        )
    if settings.env == "desktop":
        # DNS rebinding (ADR-0008): only loopback Host headers reach the API. Added last, so it
        # is the outermost middleware and runs before CORS. Starlette compares the host only.
        app.add_middleware(
            TrustedHostMiddleware, allowed_hosts=list(LOOPBACK_HOSTS), www_redirect=False
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

    app.include_router(auth.router)
    app.include_router(me.router)
    app.include_router(tuning.router)
    app.include_router(uploads.router)
    app.include_router(jobs.router)
    app.include_router(tabs.router)
    app.include_router(references.router)
    if local:
        app.include_router(local_storage.router)
    if settings.env == "desktop":
        app.include_router(imports.router)  # YouTube import: one local user (ADR-0014)
    return app
