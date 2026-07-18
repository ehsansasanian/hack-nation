"""Auto-analysis orchestrator: chain the existing reasoning stages end to end.

``analyze_application`` runs the same functions the standalone endpoints call -
``score_application`` (thesis filter + screening + 3-axis scoring) ->
``run_diligence`` -> ``generate_memo`` - stamping ``Application.analysis_status``
before each stage so a UI can render live progress. It ends in one of three
terminal states:

* ``ready``        - the whole chain completed and a memo exists.
* ``screened_out`` - screening honestly rejected the application; the chain stops
  there (no wasted diligence/memo LLM calls). Not a failure.
* ``failed``       - an unexpected error; ``analysis_error`` carries the reason and
  the chain never hangs.

The dual backend already falls back to the offline deterministic path when a live
call fails, so a fallback is *not* a failure - the chain still reaches ``ready``.

Each stage opens its own short-lived ``Session`` because analysis runs in a
background thread (FastAPI ``BackgroundTasks``), decoupled from the request that
scheduled it.

Concurrency guard: a module-level set of in-flight application ids, protected by a
lock, prevents the same application from being analysed twice at once. This is an
in-process guard only - it is sufficient for the single-process demo but would not
coordinate across multiple workers/replicas.
"""

from __future__ import annotations

import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Application
from app.reasoning.diligence import run_diligence
from app.reasoning.memo import generate_memo
from app.reasoning.service import score_application

# --- in-process concurrency guard -------------------------------------------

_inflight: set[int] = set()
_inflight_lock = threading.Lock()


def acquire(application_id: int) -> bool:
    """Atomically claim an application for analysis. False if already in flight."""
    with _inflight_lock:
        if application_id in _inflight:
            return False
        _inflight.add(application_id)
        return True


def release(application_id: int) -> None:
    with _inflight_lock:
        _inflight.discard(application_id)


def is_inflight(application_id: int) -> bool:
    with _inflight_lock:
        return application_id in _inflight


# --- status transitions -----------------------------------------------------


def derive_analysis_status(app: Application) -> str:
    """The analysis stage implied by how far the persisted pipeline got.

    Used to (re)stamp status after the batch CLIs (score_all / diligence_all) and
    demo_seed, which drive the same stages without going through the live chain.
    """
    if app.memo is not None:
        return "ready"
    if app.status == "screened_out":
        return "screened_out"
    if app.scores:
        return "scoring"
    return "received"


def stamp_analysis_status(session: Session) -> None:
    """Reconcile every application's analysis_status with its persisted progress."""
    for app in session.scalars(select(Application)):
        app.analysis_status = derive_analysis_status(app)
    session.commit()


def _set_status(application_id: int, status: str, error: str | None = None) -> None:
    """Persist the analysis stage in its own session (background-safe)."""
    with SessionLocal() as session:
        app = session.get(Application, application_id)
        if app is None:
            return
        app.analysis_status = status
        app.analysis_error = error
        session.commit()


def analyze_application(application_id: int, prefer_backend: str | None = None) -> str:
    """Run the full chain, updating ``analysis_status`` before each stage.

    Returns the terminal status (``ready`` / ``screened_out`` / ``failed``). Never
    raises: any error is captured onto ``analysis_error`` and reported as ``failed``.
    """
    try:
        # 1. Screening + scoring (one call; screening is the gate that can reject).
        _set_status(application_id, "screening")
        with SessionLocal() as session:
            outcome = score_application(session, application_id, prefer_backend=prefer_backend)
        if outcome.status == "screened_out" or not outcome.scores:
            # Honest terminal outcome - stop the chain, don't spend diligence/memo calls.
            _set_status(application_id, "screened_out")
            return "screened_out"

        # Scoring finished; surface it as its own stepper beat before diligence.
        _set_status(application_id, "scoring")

        # 2. Diligence: claim extraction -> truth-gap -> validator.
        _set_status(application_id, "diligence")
        with SessionLocal() as session:
            run_diligence(session, application_id, prefer_backend=prefer_backend)

        # 3. Memo: five sections + a scores-tied recommendation.
        _set_status(application_id, "memo")
        with SessionLocal() as session:
            generate_memo(session, application_id, prefer_backend=prefer_backend)

        _set_status(application_id, "ready")
        return "ready"
    except Exception as exc:  # noqa: BLE001 - never let a background run hang or crash silently
        _set_status(application_id, "failed", error=f"{type(exc).__name__}: {exc}")
        return "failed"


def run_analysis_task(application_id: int, prefer_backend: str | None = None) -> None:
    """BackgroundTasks entry point: run the chain and always release the guard."""
    try:
        analyze_application(application_id, prefer_backend=prefer_backend)
    finally:
        release(application_id)
