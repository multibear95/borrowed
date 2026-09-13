import asyncio
from collections import Counter

from borrowed_backend.domain.availability import check
from borrowed_backend.domain.models import SearchRequest
from borrowed_backend.domain.ranking import score
from borrowed_backend.tools.definitions import search_garments


def test_hero(store):
    req = SearchRequest(city="Hamburg", sizes_eu=[38], wear_date="2026-09-18", limit=1000)
    counts = Counter()
    for garment in store.garments.values():
        if garment.category == "dress":
            result = check(garment, req, store.today())
            counts[result.reason or "FEASIBLE"] += 1
    assert counts == {"FEASIBLE": 22, "OVERLAPS_BOOKING": 21, "WRONG_CITY": 66,
                      "SIZE_MISMATCH": 69, "TOO_LATE_TO_SHIP": 72}
    hits = asyncio.run(search_garments(store, req))
    assert len(hits) == 22
    assert all(hit.feasibility.feasible for hit in hits)
    assert hits == sorted(hits, key=lambda hit: (-hit.score, hit.garment.rental_price, hit.garment.id))
    assert len(asyncio.run(search_garments(store, req.model_copy(update={"limit": 20})))) == 20
    assert asyncio.run(search_garments(store, req)) == hits


def test_budget_and_soft_preferences(store):
    req = SearchRequest(city="Hamburg", sizes_eu=[38], wear_date="2026-09-18", limit=1000)
    base = asyncio.run(search_garments(store, req))
    colour = next(hit.garment.colour_family for hit in base if hit.garment.colour_family)
    colour_matches = asyncio.run(search_garments(store, req.model_copy(update={
        "colour_family": colour, "occasion": "weekend", "style_hints": ["unknown"]})))
    assert colour_matches
    assert all(hit.garment.colour_family.casefold() == colour.casefold() for hit in colour_matches)
    assert asyncio.run(search_garments(store, req.model_copy(update={"colour_family": "not-a-colour"}))) == []
    budget = asyncio.run(search_garments(store, req.model_copy(update={"max_price": 60})))
    assert all(h.garment.rental_price <= 60 for h in budget)
    assert asyncio.run(search_garments(store, req.model_copy(update={"max_price": 0}))) == []


def test_score_cap_and_tiebreak(store, garment):
    req = SearchRequest(city="Hamburg", sizes_eu=[38], wear_date="2026-09-18",
                        colour_family="black", occasion="gala", style_hints=["a", "b", "c", "d", "a"])
    changed = garment.model_copy(update={"colour_family": "black", "style_tags": ["a", "b", "c", "d"]})
    assert score(changed, req) == 11
    assert score(changed.model_copy(update={"colour_family": None}), req) == 8
    store.garments = {"b": changed.model_copy(update={"id": "b"}),
                      "a": changed.model_copy(update={"id": "a"}),
                      "c": changed.model_copy(update={"id": "c", "rental_price": 40})}
    assert [h.garment.id for h in asyncio.run(search_garments(store, req))] == ["c", "a", "b"]


def test_bags_skip_size(store):
    req = SearchRequest(city="Hamburg", sizes_eu=[38], wear_date="2026-09-18", category="bag")
    hits = asyncio.run(search_garments(store, req))
    assert hits and all(h.garment.category == "bag" and h.feasibility.feasible for h in hits)
