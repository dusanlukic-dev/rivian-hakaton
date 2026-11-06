from app.domain.trip import Trip


class InMemoryTripRepository:
    """Good enough for the hackathon demo; swap for SQLite/Postgres behind the same methods."""

    def __init__(self) -> None:
        self._trips: dict[str, Trip] = {}

    def add(self, trip: Trip) -> None:
        self._trips[trip.id] = trip

    def get(self, trip_id: str) -> Trip | None:
        return self._trips.get(trip_id)

    def active(self) -> Trip | None:
        """The trip currently in progress (one car = at most one active trip)."""
        return next((t for t in reversed(self._trips.values()) if t.ended_at is None), None)

    def list(self, driver_id: str | None = None) -> list[Trip]:
        trips = list(self._trips.values())
        if driver_id is not None:
            trips = [t for t in trips if t.driver_id == driver_id]
        return trips


_repository = InMemoryTripRepository()


def get_trip_repository() -> InMemoryTripRepository:
    return _repository
