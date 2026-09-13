import asyncio
from typing import Awaitable, Callable, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from borrowed_backend.api.sse import Availability, BookingClaim, Error, Event, Question, Results, Token
from borrowed_backend.data.store import InMemoryStore
from borrowed_backend.domain.errors import Conflict
from borrowed_backend.domain.models import CreateBookingIn
from borrowed_backend.tools.registry import invoke
from .llm import BorrowerLLM
from .state import BorrowerState, Turn


class GraphState(TypedDict):
    state: BorrowerState


class BorrowerGraph:
    def __init__(self, store: InMemoryStore, llm: BorrowerLLM):
        self.store = store
        self.llm = llm

    async def run(self, conversation_id: str, turn: Turn,
                  emit: Callable[[Event], Awaitable[None]]) -> None:
        store = self.store
        timeout = store.settings.llm_timeout_s
        hits = []

        async def save(state: BorrowerState, node: str) -> GraphState:
            state = state.model_copy(update={"last_node": node})
            await store.checkpoint(conversation_id, state)
            return {"state": state}

        async def extract_slots(data: GraphState):
            state = data["state"]
            if state.result_id is not None:
                state = (await save(state.model_copy(update={
                    "result_ids": [], "result_id": None, "result_request": None,
                }), "invalidate_results"))["state"]
            async with asyncio.timeout(timeout):
                extraction = await self.llm.extract({
                    "text": turn.text, "today": store.today().isoformat(),
                    "slots": state.slots.model_dump(mode="json"),
                    "missing_fields": state.slots.missing(),
                })
            slots = extraction.merge(state.slots, store.today())
            changes = {"slots": slots}
            if slots != state.slots:
                changes.update(result_ids=[], result_id=None, result_request=None)
            return await save(state.model_copy(update=changes), "extract_slots")

        async def gate(data: GraphState):
            return await save(data["state"], "gate")

        async def ask_missing(data: GraphState):
            state = data["state"]
            fields = state.slots.missing()
            # Emit a usable question even if the language service is unavailable.
            labels = {"wear_date": "wear date (including year)",
                      "city": "city", "sizes_eu": "EU size"}
            fallback = "Please provide: " + ", ".join(labels[key] for key in fields)
            chunks = []
            try:
                async with asyncio.timeout(timeout):
                    async for chunk in self.llm.text_stream({"kind": "question", "text": turn.text,
                                                             "fields": fields}):
                        chunks.append(chunk)
                message = "".join(chunks).strip() or fallback
            except Exception:
                message = fallback
                await emit(Error(code="LLM_UNAVAILABLE", message="I could not generate a reply. Please provide the details requested."))
            result = await save(state, "ask_missing")
            await emit(Question(text=message, fields=fields))
            return result

        async def search(data: GraphState):
            nonlocal hits
            state = data["state"]
            # A chat recommendation is a curated preview, so keep the card grid
            # aligned with the three garments the assistant describes.
            request = state.slots.search_request().model_copy(update={"limit": 3})
            hits = await invoke("search_garments", store, request)
            result_id = uuid4().hex
            result = await save(state.model_copy(update={
                "result_ids": [hit.garment.id for hit in hits],
                "result_id": result_id, "result_request": request,
            }), "search")
            await emit(Results(hits=hits, result_id=result_id))
            return result

        async def compose(data: GraphState):
            context = {"kind": "results" if hits else "no_results", "text": turn.text,
                       "hits": [hit.model_dump(mode="json") for hit in hits[:3]]}
            if not hits:
                await emit(Token(text="No garments match these details yet. Try another date, city, EU size or budget."))
            async with asyncio.timeout(timeout):
                async for chunk in self.llm.text_stream(context):
                    await emit(Token(text=chunk))
            return await save(data["state"], "compose")

        async def book(data: GraphState):
            state = data["state"]
            if (not turn.confirmed or not turn.garment_id or not turn.result_id
                    or turn.result_id != state.result_id
                    or turn.garment_id not in state.result_ids
                    or state.result_request is None
                    or state.slots.missing()
                    or state.slots.search_request().model_copy(update={
                        "limit": state.result_request.limit,
                    }) != state.result_request):
                await emit(Error(code="CONFIRMATION_REQUIRED", message=(
                    "Search first, then explicitly confirm one of the recommended garments. "
                    "A reservation holds the garment immediately and takes no payment.")))
                return await save(state, "book_rejected")
            request = state.result_request
            payload = CreateBookingIn(
                garment_id=turn.garment_id, city=request.city, sizes_eu=request.sizes_eu,
                wear_date=request.wear_date, return_date=request.return_date,
                idempotency_key=f"conversation:{conversation_id}:{state.result_id}:{turn.garment_id}",
            )
            try:
                booking = await invoke("create_booking", store, payload)
            except Conflict as exc:
                await emit(Availability(feasibility=exc.feasibility,
                                        garment=store.get(turn.garment_id).public()))
                await emit(Error(code="BOOKING_CONFLICT", message="This garment is no longer available. Search again or adjust the date."))
                return await save(state, "book_conflict")
            # The booking snapshot is already durable; report success before optional chat persistence.
            await emit(BookingClaim(booking=booking))
            return await save(state, "book")

        builder = StateGraph(GraphState)
        for name, handler in (("extract_slots", extract_slots), ("gate", gate),
                              ("ask_missing", ask_missing), ("search", search),
                              ("compose", compose), ("book", book)):
            builder.add_node(name, handler)
        builder.add_conditional_edges(START, lambda _: "book" if turn.intent == "book" else "extract_slots")
        builder.add_edge("extract_slots", "gate")
        builder.add_conditional_edges("gate", lambda data: "ask_missing" if data["state"].slots.missing() else "search")
        builder.add_edge("search", "compose")
        for name in ("ask_missing", "compose", "book"):
            builder.add_edge(name, END)
        await builder.compile().ainvoke({"state": store.conversations[conversation_id].slots})
