from borrowed_backend.data.store import InMemoryStore
from borrowed_backend.domain.availability import check
from borrowed_backend.domain.models import (
    BookingResult, CheckAvailabilityIn, CreateBookingIn, Feasibility,
    GarmentPublic, GetGarmentIn, SearchHit, SearchRequest,
)
from borrowed_backend.domain.ranking import score
from .registry import tool


@tool(name="search_garments", description=(
    "Use to find available garments for a city, EU size and explicit wear date. "
    "For dresses, ask for sizes_eu before calling. Returns feasible matches only, "
    "with price, score and logistics dates. return_date is the last wear day (inclusive); "
    "omit to use the garment rental period. Empty results mean no match, not an error."
),
      input=SearchRequest, output=list[SearchHit])
async def search_garments(store: InMemoryStore, req: SearchRequest) -> list[SearchHit]:
    hits = []
    today = store.today()
    for garment in store.garments.values():
        if garment.category != req.category:
            continue
        if (req.colour_family is not None and
                (garment.colour_family is None or
                 garment.colour_family.casefold() != req.colour_family.casefold())):
            continue
        feasibility = check(garment, req, today)
        if not feasibility.feasible:
            continue
        if req.max_price is not None and garment.rental_price > req.max_price:
            continue
        hits.append(SearchHit(garment=garment.public(), feasibility=feasibility, score=score(garment, req)))
    hits.sort(key=lambda hit: (-hit.score, hit.garment.rental_price, hit.garment.id))
    return hits[:req.limit]


@tool(name="get_garment", description=(
    "Use to get details for a garment_id returned by search. This does not confirm "
    "availability; use check_availability for specific dates. Image paths are server-relative."
), input=GetGarmentIn, output=GarmentPublic)
async def get_garment(store: InMemoryStore, req: GetGarmentIn) -> GarmentPublic:
    return store.get(req.garment_id).public()


@tool(name="check_availability", description=(
    "Use to check a garment for a city, EU sizes and wear dates. Returns feasible, "
    "logistics dates and a reason when unavailable. return_date is the last wear day "
    "(inclusive). This check does not place a hold."
),
      input=CheckAvailabilityIn, output=Feasibility)
async def check_availability(store: InMemoryStore, req: CheckAvailabilityIn) -> Feasibility:
    return check(store.get(req.garment_id), req, store.today())


@tool(name="create_booking", description=(
    "Places a **real hold** on the garment for these dates. The garment immediately "
    "becomes unavailable to every other borrower. **No payment is taken and no card is "
    "charged** — this reserves the item only."
    " Use only after the user explicitly confirms the garment and dates. "
    "return_date is the last wear day, inclusive. Supply a unique idempotency_key "
    "and reuse that key and the same arguments for retries."
), input=CreateBookingIn, output=BookingResult, scope="booking:write")
async def create_booking(store: InMemoryStore, req: CreateBookingIn) -> BookingResult:
    return await store.create_booking(req)
