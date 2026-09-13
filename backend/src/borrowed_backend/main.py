from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.routing import Route

from borrowed_backend.api.routes import router
from borrowed_backend.api.conversations import router as conversations_router
from borrowed_backend.agents.llm import BorrowerLLM, OpenAILLM
from borrowed_backend.config import Settings
from borrowed_backend.data.store import InMemoryStore
from borrowed_backend.domain.errors import Conflict, IdempotencyConflict, NotFound, PersistenceFailure
from borrowed_backend.tools import definitions as _definitions
from borrowed_backend.tools.adapters.mcp_server import MCPAdapter


def create_app(settings: Settings | None = None, *, borrower_llm: BorrowerLLM | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = InMemoryStore(settings)
        app.state.borrower_llm = borrower_llm or OpenAILLM(settings)
        try:
            async with mcp.manager.run():
                yield
        finally:
            await app.state.borrower_llm.close()

    app = FastAPI(title="borrowed — stage 2", lifespan=lifespan)
    mcp = MCPAdapter(settings, lambda: app.state.store)
    # ASGI routes preserve MCP request bodies and avoid a /mcp -> /mcp/ redirect.
    app.router.routes.append(Route("/mcp", endpoint=mcp, methods=["GET", "POST", "DELETE"]))
    app.include_router(router)
    app.include_router(conversations_router)
    app.mount("/images", StaticFiles(directory=settings.images_dir), name="images")

    @app.exception_handler(NotFound)
    async def not_found(request: Request, exc: NotFound):
        return JSONResponse(status_code=404, content={"reason": "GARMENT_NOT_FOUND"})

    @app.exception_handler(Conflict)
    async def conflict(request: Request, exc: Conflict):
        return JSONResponse(status_code=409, content={
            "reason": exc.feasibility.reason,
            "feasibility": exc.feasibility.model_dump(mode="json"),
        })

    @app.exception_handler(IdempotencyConflict)
    async def idempotency_conflict(request: Request, exc: IdempotencyConflict):
        return JSONResponse(status_code=409, content={"reason": "IDEMPOTENCY_KEY_REUSED"})

    @app.exception_handler(PersistenceFailure)
    async def persistence_failure(request: Request, exc: PersistenceFailure):
        return JSONResponse(status_code=503, content={"reason": "PERSISTENCE_FAILED"})

    @app.exception_handler(OverflowError)
    async def invalid_date_range(request: Request, exc: OverflowError):
        return JSONResponse(status_code=422, content={"reason": "DATE_RANGE_OUT_OF_BOUNDS"})

    return app
