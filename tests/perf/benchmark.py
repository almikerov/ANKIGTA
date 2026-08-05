"""Take every measurement ticket 30 states a threshold for.

What each measurement covers, and what it does not, is written into its own
`context`. That is not documentation politeness: several of these thresholds
are about something ANKIGTA only partly owns. The Card Picker's first page is
ANKIGTA reading and shaping cards *after* Anki's own search returned; a card
opening ends in stock MTA CEF; a rating ends in Anki's scheduler. Reporting a
number without saying which part it is would be reporting a number for a
promise nobody made.

Nothing here drives a GUI, and nothing writes inside an installed MTA or Anki
tree. The Lua measurements run the real resource scripts in the same Lua 5.1
MTA embeds; the companion measurements run the real modules over real loopback
HTTP.
"""

from __future__ import annotations

import json
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from http.client import HTTPConnection
from pathlib import Path
from threading import Event
from typing import Any, Callable, Iterator, Sequence
from xml.etree import ElementTree

from ankigta_companion.cards import CardPickerService, CardView
from ankigta_companion.collection_identity import (
    AnkiCardIdentity,
    CollectionIdentityObservation,
    CollectionIdentityState,
)
from ankigta_companion.content import ContentServer, RenderedCard
from ankigta_companion.eligibility import EligibilitySettings, classify
from ankigta_companion.contract import (
    CollectionObservation,
    CollectionState,
    RuntimeObservation,
)
from ankigta_companion.http_server import HealthServer
from ankigta_companion.journal import ReviewJournal
from ankigta_companion.review import ReviewCoordinator
from ankigta_companion.session import (
    FILTERED_DECK_NAME,
    FilteredDeckInfo,
    SessionCoordinator,
)

from tests.lua import MtaSandbox

from .dataset import ReferenceDataset, deck_name, fill_store, reference_dataset
from .environment import describe_machine
from .report import Measurement, PerformanceReport, build_report


REPO_ROOT = Path(__file__).resolve().parents[2]
RESOURCE_ROOT = REPO_ROOT / "mta" / "ankigta"

#: A p95 over fewer than twenty samples is the maximum wearing a percentile's
#: name, so twenty is the floor wherever the ticket says "for 95%".
PERCENTILE_SAMPLES = 20
#: The thresholds stated as a ceiling are sampled cold once and warm after, and
#: reported as the worst of them. More repeats would not change a maximum.
CEILING_SAMPLES = 6
#: Frames simulated per batch for the per-frame budget, and how many batches.
FRAME_SAMPLES = 120
FRAME_BATCHES = 8
#: Polls per batch. Far fewer than frames, because one poll walks the whole
#: reference world and eight batches of a hundred and twenty would be a minute
#: of benchmark for a number that settles in a handful.
POLL_SAMPLES = 8
#: Session rebuilds: the first build, then repeats, so the number is not only
#: the first-ever one.
REBUILD_SAMPLES = 3


def _scripts(*kinds: str) -> list[str]:
    manifest = ElementTree.parse(RESOURCE_ROOT / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in kinds
    ]


def _milliseconds(started: float) -> float:
    return (time.perf_counter() - started) * 1000.0


@contextmanager
def _server_side(dataset: ReferenceDataset) -> Iterator[MtaSandbox]:
    """The whole server side, started on a real database holding the world."""
    with tempfile.TemporaryDirectory(prefix="ankigta-perf-") as directory:
        sandbox = MtaSandbox(database_path=str(Path(directory) / "ankigta.sqlite"))
        try:
            for script in _scripts("shared", "server"):
                sandbox.load(script)
            sandbox.trigger("onResourceStart")
            fill_store(
                sandbox,
                map_entities=dataset.map_entities,
                spatial_links=dataset.spatial_links,
            )
            yield sandbox
        finally:
            sandbox.close()


@contextmanager
def _client_side() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    try:
        for script in _scripts("shared", "client"):
            sandbox.load(script)
        yield sandbox
    finally:
        sandbox.close()


# --- F7 -----------------------------------------------------------------------


def measure_f7(dataset: ReferenceDataset) -> Measurement:
    """How long the F7 snapshot takes to become available.

    The whole snapshot is what "F7 available" means: the presence refresh, the
    read of every Map Entity and the contract the client renders from.

    The store's own read is timed alongside and reported in the context rather
    than as a threshold of its own. Part of that number is the harness's: MTA
    builds a result row in C++ inside `dbPoll`, and here it is built in Python
    and handed across into Lua, which for ten thousand rows costs several times
    what SQLite spent answering. It is worth carrying because it moves when the
    query does; it is not worth holding a limit against.
    """
    open_samples: list[float] = []
    read_samples: list[float] = []
    reported_build: list[float] = []
    with _server_side(dataset) as server:
        player = server.add_study_player()
        resource_root = server.eval("resourceRoot")
        list_entities = server.eval(
            "function() return #ANKIGTA.Store.listMapEntities() end"
        )
        # Read the two numbers out in Lua. Marshalling a ten-thousand-entity
        # snapshot into Python costs about as long as building it, and that
        # cost is the harness's rather than the resource's.
        read_diagnostics = server.eval(
            "function(snapshot)"
            " return snapshot.diagnostics.buildMs, snapshot.diagnostics.entityCount"
            " end"
        )
        for index in range(CEILING_SAMPLES):
            started = time.perf_counter()
            server.trigger("ankigta:requestF7", resource_root, client=player)
            open_samples.append(_milliseconds(started))
            sent = server.recorder.client_events[-1]
            if sent.name != "ankigta:f7Snapshot":
                return Measurement(
                    key="f7_available",
                    unavailable_reason=f"F7 was refused: {sent.name}",
                )
            build_ms, entities = read_diagnostics(sent.args[0])
            reported_build.append(float(build_ms))
            entity_count = int(entities)

            started = time.perf_counter()
            served = list_entities()
            read_samples.append(_milliseconds(started))

    return Measurement(
        key="f7_available",
        samples=tuple(open_samples),
        context={
            "measures": (
                "onResourceStart to the f7Snapshot event: presence refresh, "
                "the store read, and the contract every entity is rendered from"
            ),
            "excludes": (
                "CEGUI drawing the window, which no automated check can time"
            ),
            "entitiesInSnapshot": entity_count,
            "rowsServed": int(served),
            "resourceReportedBuildMsMax": max(reported_build),
            "storeReadMsMax": max(read_samples),
            "storeReadNote": (
                "Store.listMapEntities alone, harness included: MTA builds a "
                "result row in C++, this harness builds it in Python"
            ),
        },
    )


def measure_search_filter(dataset: ReferenceDataset) -> Measurement:
    """The deck filter narrowing the Card Picker to its first page.

    One of the two searches the 150 ms promise covers; F7's own Map Entity
    filter is the other, and is measured as `f7_entity_filter`.

    Measured over the same loopback the Card Picker's unfiltered first page
    goes over, and differing from it only in what the query narrows to — which
    is what makes the two numbers comparable.
    """
    picker = _card_picker(dataset)
    samples: list[float] = []
    total = 0
    deck = deck_name(0)
    with HealthServer(
        lambda: _runtime_observation(dataset.collection_uuid),
        card_picker=picker,
    ) as server:
        for index in range(PERCENTILE_SAMPLES):
            started = time.perf_counter()
            response = _post(
                server.port,
                "/v1/cards/search",
                {
                    "protocol": "ankigta-control",
                    "protocolVersion": 1,
                    "requestId": f"perf-filter-{index}",
                    "query": "",
                    "deckFilter": deck,
                    "page": 0,
                    "pageSize": 50,
                },
            )
            samples.append(_milliseconds(started))
            if not response.get("ok"):
                return Measurement(
                    key="search_filter",
                    unavailable_reason=(
                        f"deck-filtered search failed: {response.get('error')}"
                    ),
                )
            total = int(response["payload"]["total"])

    return Measurement(
        key="search_filter",
        samples=tuple(samples),
        context={
            "measures": (
                'POST /v1/cards/search with deck:"..." over loopback: the '
                "handler, the narrowing, and the page that comes back"
            ),
            "excludes": (
                "Anki's own find_cards, which the reference collection answers "
                "from a generated index rather than from Anki's search"
            ),
            "companion": (
                "the other half of the same 150 ms promise is F7's own Map "
                "Entity filter, measured separately as f7_entity_filter"
            ),
            "deckFilter": deck,
            "cardsInCollection": dataset.anki_cards,
            "cardsMatched": total,
            "pageSize": 50,
        },
    )


F7_ENTITIES_LUA = """
function(count)
    local entities = {}
    for index = 1, count do
        entities[index] = {
            mapEntity = {
                mapId = "ticket30-reference",
                entityId = string.format("ref-%06d", index - 1),
                type = "object",
            },
            metadata = {
                name = "Entity " .. index,
                entityTag = "bucket-" .. (index % 20),
            },
            link = {state = "Active Spatial Link"},
        }
    end
    return entities
end
"""


def measure_f7_entity_filter(dataset: ReferenceDataset) -> Measurement:
    """F7's Map Entity filter narrowing the reference world.

    The other half of story 58's 150 ms promise, and the one story 51 asks for:
    a filter over every managed Map Entity of the loaded maps, which does not
    depend on current streaming and so is measured with no world at all.
    """
    samples: list[float] = []
    kept = 0
    with _client_side() as client:
        # Built in Lua rather than marshalled from Python: ten thousand nested
        # tables crossing the boundary would cost more than the measurement.
        entities = client.eval(F7_ENTITIES_LUA)(dataset.map_entities)
        narrow = client.eval(
            """
            function(entities, query)
                return #ANKIGTA.Panel.matching(entities, query)
            end
            """
        )
        # A query that keeps a handful out of ten thousand, which is what a
        # player types when they are looking for one door.
        narrow(entities, "ref-000123")
        for _ in range(CEILING_SAMPLES):
            started = time.perf_counter()
            kept = int(narrow(entities, "ref-000123"))
            samples.append(_milliseconds(started))

    return Measurement(
        key="f7_entity_filter",
        samples=tuple(samples),
        context={
            "measures": (
                "ANKIGTA.Panel.matching over every Map Entity in the snapshot: "
                "identity, name, Entity Tag, type and Spatial Link state"
            ),
            "excludes": (
                "CEGUI clearing and repopulating the grid with the rows that "
                "survive, which no automated check can time"
            ),
            "entities": dataset.map_entities,
            "matched": kept,
        },
    )


# --- the per-frame budget -----------------------------------------------------


#: The frame rate the per-frame budget is stated against. Story 58 says
#: "average frame time" without naming a rate, and the amortised cost of
#: anything that does not run every frame depends on one.
REFERENCE_FPS = 60.0
FRAME_MS = 1000.0 / REFERENCE_FPS

FRAME_LUA = """
function(markers, identity, frames)
    local player = {
        x = 0, y = 0, z = 0, interior = 0, dimension = 0,
        speedKmh = 0, reviewOpen = false,
    }
    for frame = 1, frames do
        -- Walk, so the marker really moves and nothing can be answered from
        -- whatever the previous frame happened to leave behind.
        player.x = frame * 0.5
        ANKIGTA.Indicator.plan(player, markers, identity)
        ANKIGTA.Indicator.hudText()
    end
end
"""

POLL_LUA = """
function(candidates, polls)
    local player = {
        x = 0, y = 0, z = 0, interior = 0, dimension = 0,
        speedKmh = 0, reviewOpen = false,
    }
    for poll = 1, polls do
        player.x = poll * 4
        ANKIGTA.Activation.update(poll, player, candidates)
    end
end
"""


def _reference_candidates(client: MtaSandbox, dataset: ReferenceDataset) -> Any:
    return client.lua.table_from(
        [
            client.lua.table_from(
                {
                    "mapId": "ticket30-reference",
                    "entityId": f"ref-{index:06d}",
                    "x": float(index % 500) * 4.0,
                    "y": float(index // 500) * 4.0,
                    "z": float(index % 7),
                    "radius": 3.0,
                    "interior": 0,
                    "dimension": 0,
                    "eligible": True,
                    "present": True,
                    "hasCorona": True,
                    "cardIdentity": client.lua.table_from(
                        {
                            "collectionUuid": dataset.collection_uuid,
                            "cardId": 1_000_000 + index,
                        }
                    ),
                }
            )
            for index in range(dataset.spatial_links)
        ]
    )


def measure_spatial_frame(dataset: ReferenceDataset) -> Measurement:
    """The average frame time the Activation Zone, the marker and the HUD add.

    Two costs, because they run at two rates. The marker and the HUD line are
    drawn every frame. The Activation Zone is not: `client/spatial.lua` polls
    the world on a timer, and the cadence it polls at is read out of the
    resource here rather than restated, so changing it moves this number.

    The scan is measured at the worst case the reference world allows -- every
    Spatial Link streamed in, eligible, and in the player's own interior and
    dimension, so nothing is skipped by a cheap check before the distance test.
    """
    samples: list[float] = []
    poll_samples: list[float] = []
    with _client_side() as client:
        candidates = _reference_candidates(client, dataset)
        # What the marker actually walks: the entities carrying one card, which
        # is what the server sends and what the runtime index resolves.
        markers = client.lua.table_from([candidates[1], candidates[2]])
        identity = client.lua.table_from(
            {"collectionUuid": dataset.collection_uuid, "cardId": 1_000_001}
        )
        interval_ms = float(
            client.eval("function() return ANKIGTA.Spatial.pollIntervalMs() end")()
        )
        client.eval(
            "function() return ANKIGTA.Indicator.setMode('sphere_and_minimap') end"
        )()
        client.eval(
            """
            function(counts)
                triggerEvent("ankigta:statistics", resourceRoot, counts)
            end
            """
        )(
            client.lua.table_from(
                {"total": 4500, "new": 1800, "learning": 900, "due": 1350, "early": 450}
            )
        )
        frame = client.eval(FRAME_LUA)
        poll = client.eval(POLL_LUA)
        # One warm-up of each: the first pass pays for Lua's own lazy work, and
        # a frame budget is about the frames after the first.
        frame(markers, identity, 10)
        poll(candidates, 1)
        for _ in range(FRAME_BATCHES):
            started = time.perf_counter()
            frame(markers, identity, FRAME_SAMPLES)
            drawn = _milliseconds(started) / FRAME_SAMPLES

            started = time.perf_counter()
            poll(candidates, POLL_SAMPLES)
            polled = _milliseconds(started) / POLL_SAMPLES

            poll_samples.append(polled)
            # A poll every `interval_ms` costs this much of every frame.
            samples.append(drawn + polled * FRAME_MS / interval_ms)

    return Measurement(
        key="spatial_frame",
        samples=tuple(samples),
        context={
            "measures": (
                "Indicator.plan and the HUD line every frame, plus "
                "Activation.update over every Spatial Link amortised at the "
                "cadence client/spatial.lua polls at"
            ),
            "excludes": (
                "dxDraw and blip calls and the element accessors the runtime "
                "index reads positions through, which are the game's cost "
                "rather than ANKIGTA's, and Pick Entity, which runs only while "
                "picking"
            ),
            "candidates": dataset.spatial_links,
            "markers": 2,
            "pollIntervalMs": interval_ms,
            "pollMsMax": max(poll_samples),
            "pollMsMedian": sorted(poll_samples)[len(poll_samples) // 2],
            "referenceFps": REFERENCE_FPS,
            "framesPerPoll": interval_ms / FRAME_MS,
            "framesPerBatch": FRAME_SAMPLES,
            "pollsPerBatch": POLL_SAMPLES,
            "batches": FRAME_BATCHES,
        },
    )


# --- the companion ------------------------------------------------------------


def _identity_observation(uuid: str) -> CollectionIdentityObservation:
    return CollectionIdentityObservation(CollectionIdentityState.BOUND, uuid)


def _runtime_observation(uuid: str) -> RuntimeObservation:
    return RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(
            state=CollectionState.OPEN,
            identity=_identity_observation(uuid),
        ),
    )


@dataclass
class _RecordingBackend:
    """A filtered-deck backend that records what it was asked to build.

    Anki's own rebuild is not measured and is not simulated with a sleep: an
    invented delay would be a number about this file rather than about ANKIGTA.
    What is measured is everything ANKIGTA does around it — deduplication,
    reading each card, classifying its eligibility, and driving the build.
    """

    top: AnkiCardIdentity | None = None

    def __post_init__(self) -> None:
        self.built: list[tuple[int, ...]] = []

    def inspect(self, name: str) -> FilteredDeckInfo | None:
        return None

    def build(
        self,
        name: str,
        card_ids: tuple[int, ...],
        *,
        progress: Callable[[int, int], None],
        cancel: Event,
    ) -> None:
        self.built.append(card_ids)
        progress(len(card_ids), len(card_ids))

    def cleanup(self, name: str) -> None:
        return None

    def scheduler_top(self) -> AnkiCardIdentity | None:
        return self.top


def _card_picker(dataset: ReferenceDataset) -> CardPickerService:
    return CardPickerService(
        lambda: _identity_observation(dataset.collection_uuid),
        lambda: dataset.collection,
        today=lambda: 0,
    )


def _post(port: int, path: str, body: dict[str, object]) -> dict[str, Any]:
    connection = HTTPConnection("127.0.0.1", port, timeout=30)
    encoded = json.dumps(body).encode("utf-8")
    connection.request(
        "POST",
        path,
        body=encoded,
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(encoded)),
        },
    )
    response = connection.getresponse()
    payload = json.loads(response.read())
    connection.close()
    return dict(payload)


def measure_card_picker_first_page(dataset: ReferenceDataset) -> Measurement:
    """The Card Picker's first page over the reference collection, over HTTP.

    End to end from the request the MTA server sends to the response it reads,
    across real loopback, through the real handler and the real service.
    """
    picker = _card_picker(dataset)
    samples: list[float] = []
    total = 0
    with HealthServer(
        lambda: _runtime_observation(dataset.collection_uuid),
        card_picker=picker,
    ) as server:
        for index in range(PERCENTILE_SAMPLES):
            started = time.perf_counter()
            response = _post(
                server.port,
                "/v1/cards/search",
                {
                    "protocol": "ankigta-control",
                    "protocolVersion": 1,
                    "requestId": f"perf-search-{index}",
                    "query": "",
                    "deckFilter": None,
                    "page": 0,
                    "pageSize": 50,
                },
            )
            samples.append(_milliseconds(started))
            if not response.get("ok"):
                return Measurement(
                    key="card_picker_first_page",
                    unavailable_reason=f"card search failed: {response.get('error')}",
                )
            total = int(response["payload"]["total"])

    return Measurement(
        key="card_picker_first_page",
        samples=tuple(samples),
        context={
            "measures": (
                "POST /v1/cards/search over loopback: the handler, the Card "
                "Picker service reading and shaping cards, and the response"
            ),
            "excludes": (
                "Anki's own find_cards, which the reference collection answers "
                "from a generated index rather than from Anki's search"
            ),
            "cardsInCollection": dataset.anki_cards,
            "cardsMatched": total,
            "pageSize": 50,
        },
    )


def measure_card_open(dataset: ReferenceDataset) -> Measurement:
    """Issuing a render capability and fetching the card document.

    This is the whole of what ANKIGTA owns when a card opens. What happens next
    is stock MTA CEF laying the document out, which is neither ANKIGTA's code
    nor something an automated check may drive.
    """
    identity = dataset.linked_identities[0]
    html = "<p>front</p>" + ("<span>word</span>" * 200)

    def render(target: AnkiCardIdentity, side: str) -> RenderedCard | None:
        card = dataset.collection.get_card(target.card_id)
        if card is None:
            return None
        return RenderedCard(html=f"<!-- {side} -->{html}", media={})

    samples: list[float] = []
    content = ContentServer(render)
    content.start()
    try:
        for _ in range(PERCENTILE_SAMPLES):
            started = time.perf_counter()
            capability = content.issue(identity, "question")
            connection = HTTPConnection("127.0.0.1", content.port, timeout=30)
            connection.request("GET", capability.document_path)
            response = connection.getresponse()
            body = response.read()
            connection.close()
            samples.append(_milliseconds(started))
            if response.status != 200 or not body:
                return Measurement(
                    key="card_open",
                    unavailable_reason=(
                        f"card document was not served: HTTP {response.status}"
                    ),
                )
    finally:
        content.stop()

    return Measurement(
        key="card_open",
        samples=tuple(samples),
        context={
            "measures": (
                "issuing a render capability and fetching the card document "
                "over the content endpoint"
            ),
            "excludes": (
                "stock MTA CEF laying the document out, which only a human can "
                "observe (ADR 0027)"
            ),
            "documentBytes": len(html),
        },
    )


def measure_rating_confirmation(dataset: ReferenceDataset) -> Measurement:
    """Admitting one exact card and applying its rating, over HTTP.

    Every part of Exact Card Admission ANKIGTA owns is in here, including the
    journal's write before the scheduler is called — which is a real file
    write, and the part of a rating most likely to be slow on a real disk.
    """
    backend = _RecordingBackend()
    picker = _card_picker(dataset)
    # Only cards the scheduler would admit: a rating measurement on a card that
    # is refused before the deck is touched would time a rejection.
    rateable = [
        identity
        for identity in dataset.linked_identities
        if _is_rateable(picker, identity)
    ][:PERCENTILE_SAMPLES]
    if not rateable:
        return Measurement(
            key="rating_confirmation",
            unavailable_reason="the reference collection admitted no card",
        )

    def read(card_id: int) -> CardView | None:
        try:
            return picker.read(card_id)
        except Exception:
            return None

    session = SessionCoordinator(
        observe=lambda: _runtime_observation(dataset.collection_uuid),
        read_card=read,
        backend=backend,
    )
    session.start(rateable, allow_early_review=False)
    samples: list[float] = []
    with tempfile.TemporaryDirectory(
        prefix="ankigta-perf-journal-",
        # Windows will not delete a SQLite file whose write-ahead log the
        # process still holds; the journal is closed below, and the directory
        # is temporary either way.
        ignore_cleanup_errors=True,
    ) as directory:
        journal = ReviewJournal(Path(directory) / "review-journal.sqlite")
        review = ReviewCoordinator(
            session=session,
            answer_card=lambda card_id, ease: None,
            journal=journal,
        )
        with HealthServer(
            lambda: _runtime_observation(dataset.collection_uuid),
            session_coordinator=session,
            review_coordinator=review,
        ) as server:
            for index, identity in enumerate(rateable):
                backend.top = identity
                started = time.perf_counter()
                admitted = _post(
                    server.port,
                    "/v1/session/admit",
                    {
                        "protocol": "ankigta-control",
                        "protocolVersion": 1,
                        "requestId": f"perf-admit-{index}",
                        "cardIdentity": {
                            "collectionUuid": identity.collection_uuid,
                            "cardId": identity.card_id,
                        },
                        "allowEarlyReview": False,
                    },
                )
                if not admitted.get("ok"):
                    journal.close()
                    return Measurement(
                        key="rating_confirmation",
                        unavailable_reason=(
                            f"admission failed: {admitted.get('error')}"
                        ),
                    )
                rated = _post(
                    server.port,
                    "/v1/review/rate",
                    {
                        "protocol": "ankigta-control",
                        "protocolVersion": 1,
                        "requestId": f"perf-rate-{index}",
                        "reviewTransactionId": f"perf-transaction-{index}",
                        "cardIdentity": {
                            "collectionUuid": identity.collection_uuid,
                            "cardId": identity.card_id,
                        },
                        "rating": "good",
                    },
                )
                samples.append(_milliseconds(started))
                if not rated.get("ok"):
                    journal.close()
                    return Measurement(
                        key="rating_confirmation",
                        unavailable_reason=f"rating failed: {rated.get('error')}",
                    )
        journal.close()

    return Measurement(
        key="rating_confirmation",
        samples=tuple(samples),
        context={
            "measures": (
                "POST /v1/session/admit then POST /v1/review/rate over "
                "loopback, including the Review Journal's durable write"
            ),
            "excludes": (
                "Anki's scheduler applying the answer, which is Anki's own "
                "cost and is never driven by an automated check"
            ),
            "ratings": len(samples),
        },
    )


def _is_rateable(picker: CardPickerService, identity: AnkiCardIdentity) -> bool:
    """Would the eligibility rule let this card be rated without early review?

    Asked through the rule itself rather than by re-deriving it here: a second
    copy of "which cards may be rated" is a second answer waiting to disagree.
    """
    try:
        card = picker.read(identity.card_id)
    except Exception:
        return False
    return classify(
        card,
        EligibilitySettings(allow_early_review=False, early_review_supported=True),
        None,
    ).rateable


def measure_session_rebuild(dataset: ReferenceDataset) -> Measurement:
    """Building the full session from every Spatial Link in the world."""
    backend = _RecordingBackend()
    picker = _card_picker(dataset)

    def read(card_id: int) -> CardView | None:
        try:
            return picker.read(card_id)
        except Exception:
            return None

    session = SessionCoordinator(
        observe=lambda: _runtime_observation(dataset.collection_uuid),
        read_card=read,
        backend=backend,
    )
    progress_seen: list[tuple[int, int]] = []
    samples: list[float] = []
    started = time.perf_counter()
    result = session.start(
        dataset.linked_identities,
        allow_early_review=False,
        progress=lambda done, total: progress_seen.append((done, total)),
    )
    samples.append(_milliseconds(started))
    # Repeats, so the number is not only the first-ever build.
    for _ in range(REBUILD_SAMPLES - 1):
        started = time.perf_counter()
        session.rebuild(dataset.linked_identities, allow_early_review=False)
        samples.append(_milliseconds(started))

    return Measurement(
        key="session_rebuild",
        samples=tuple(samples),
        context={
            "measures": (
                "SessionCoordinator.start over every linked identity: "
                "deduplication, reading each card, eligibility, and the build"
            ),
            "excludes": (
                "Anki rebuilding the filtered deck, which is Anki's own work"
            ),
            "identities": len(dataset.linked_identities),
            "admitted": len(result.card_ids),
            "skipped": len(result.skipped),
            "progressReported": bool(progress_seen),
        },
    )


# --- the whole run ------------------------------------------------------------


def run_benchmark(
    dataset: ReferenceDataset | None = None,
    *,
    mta_server_root: str | None = None,
) -> PerformanceReport:
    world = dataset if dataset is not None else reference_dataset()
    measurements = [
        measure_f7(world),
        measure_search_filter(world),
        measure_f7_entity_filter(world),
        measure_spatial_frame(world),
        measure_card_picker_first_page(world),
        measure_card_open(world),
        measure_rating_confirmation(world),
        measure_session_rebuild(world),
    ]
    return build_report(
        measurements,
        machine=describe_machine(mta_server_root=mta_server_root),
        dataset={
            "mapEntities": world.map_entities,
            "spatialLinks": world.spatial_links,
            "ankiCards": world.anki_cards,
            "uniqueLinkedCards": len(world.linked_identities),
            "collectionUuid": world.collection_uuid,
        },
        runs=("cold", "warm"),
    )
