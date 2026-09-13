"""Authless demo MCP transport; business logic stays in the registry."""

import json
import logging
from collections.abc import Callable

from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations
from pydantic import TypeAdapter, ValidationError, create_model

from borrowed_backend.config import Settings
from borrowed_backend.data.store import InMemoryStore
from borrowed_backend.domain.errors import Conflict, IdempotencyConflict, NotFound, PersistenceFailure
from borrowed_backend.tools.registry import REGISTRY, invoke

logger = logging.getLogger(__name__)


def tool_result(payload: dict, *, error: bool = False) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
        structuredContent=payload, isError=error,
    )


class MCPAdapter:
    def __init__(self, settings: Settings, get_store: Callable[[], InMemoryStore]):
        self.server = Server("MORE", version="0.1.0", instructions=(
            "MORE is a garment rental demo. Ask for city, EU size (for dresses), and an "
            "explicit wear date before searching. return_date means the last wear day, "
            "inclusive, not the delivery-back date. Omit it to use the garment's rental period. "
            "Use only the returned feasibility and dates; never invent availability. "
            "Successful tool data is inside result. Image paths are relative to this server. "
            "Before create_booking, show the garment and dates and obtain explicit user "
            "confirmation. It creates a real hold, with no payment. Generate a unique "
            "idempotency_key per reservation and reuse it for retries of the same request. "
            "This demo has no authentication; all clients share inventory and reservation keys."
        ))

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [Tool(
                name=definition.name, description=definition.description,
                inputSchema=definition.input.model_json_schema(),
                outputSchema=create_model(
                    f"{definition.name}Result", result=(definition.output, ...),
                ).model_json_schema(),
                annotations=ToolAnnotations(
                    readOnlyHint=definition.scope == "read",
                    destructiveHint=definition.scope != "read",
                    # Read tools have no side effects. Booking is idempotent by key.
                    idempotentHint=definition.scope == "read" or definition.name == "create_booking",
                    openWorldHint=False,
                ),
            ) for definition in REGISTRY.values() if definition.external]

        # The registry performs the same Pydantic validation as REST and the graph.
        @self.server.call_tool(validate_input=False)
        async def call_tool(name: str, arguments: dict) -> CallToolResult:
            definition = REGISTRY.get(name)
            if definition is None or not definition.external:
                return tool_result({"reason": "UNKNOWN_TOOL"}, error=True)
            try:
                result = await invoke(name, get_store(), arguments)
                payload = TypeAdapter(definition.output).dump_python(result, mode="json")
                return tool_result({"result": payload})
            except ValidationError as exc:
                return tool_result({"reason": "INVALID_ARGUMENTS", "issues": [
                    {"field": list(issue["loc"]), "type": issue["type"]}
                    for issue in exc.errors()
                ]}, error=True)
            except NotFound:
                return tool_result({"reason": "GARMENT_NOT_FOUND"}, error=True)
            except Conflict as exc:
                return tool_result({"reason": exc.feasibility.reason,
                                    "feasibility": exc.feasibility.model_dump(mode="json")}, error=True)
            except IdempotencyConflict:
                return tool_result({"reason": "IDEMPOTENCY_KEY_REUSED"}, error=True)
            except PersistenceFailure:
                return tool_result({"reason": "PERSISTENCE_FAILED"}, error=True)
            except OverflowError:
                return tool_result({"reason": "DATE_RANGE_OUT_OF_BOUNDS"}, error=True)
            except Exception:
                logger.exception("MCP tool failed: %s", name)
                return tool_result({"reason": "INTERNAL_ERROR"}, error=True)

        self.manager = StreamableHTTPSessionManager(
            app=self.server, stateless=True, json_response=True,
            security_settings=TransportSecuritySettings(
                allowed_hosts=settings.mcp_allowed_hosts,
                allowed_origins=settings.mcp_allowed_origins,
            ),
        )

    async def __call__(self, scope, receive, send):
        await self.manager.handle_request(scope, receive, send)
