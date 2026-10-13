"""Own-record lifecycle with visible, bounded prerequisite recovery."""
import copy
import logging
from dataclasses import dataclass

from booker_qa.client import BookerClient
from booker_qa.data import booking_payload

log = logging.getLogger(__name__)


@dataclass
class BookingHandle:
    booking_id: int
    payload: dict


class BookingRegistry:
    def __init__(self, client: BookerClient):
        self.client = client
        self.ids = []
        self.recoveries = []

    def create(self, payload=None, *, client=None):
        data = copy.deepcopy(payload if payload is not None else booking_payload())
        response = (client or self.client).request("POST", "/booking", json=data)
        response.raise_for_status()
        body = response.json()
        booking_id = body["bookingid"]
        if not isinstance(booking_id, int) or isinstance(booking_id, bool):
            raise ValueError("Invalid booking ID")
        # Register before validating the returned booking so cleanup survives bad contracts.
        self.ids.append(booking_id)
        return BookingHandle(booking_id, data), body["booking"]

    def ensure(self, handle: BookingHandle, *, max_recreates=1):
        """Recover only prerequisites; assertions after an operation never use this."""
        for attempt in range(max_recreates + 1):
            response = self.client.request("GET", f"/booking/{handle.booking_id}")
            if response.status_code != 404:
                response.raise_for_status()
                return response.json()
            if attempt == max_recreates:
                raise RuntimeError("Prerequisite remained missing after bounded recovery")
            old_id = handle.booking_id
            replacement, _ = self.create(handle.payload)
            handle.booking_id = replacement.booking_id
            self.recoveries.append((old_id, handle.booking_id))
            log.warning("Recreated missing prerequisite booking %s as %s", old_id, handle.booking_id)
        raise RuntimeError("Unreachable recovery state")

    def cleanup(self):
        errors = []
        for booking_id in self.ids:
            try:
                response = self.client.request("DELETE", f"/booking/{booking_id}", authenticated=True)
                # This sandbox can return 405 on repeated DELETE. Accept it only
                # after a GET proves the record is absent, never unconditionally.
                if response.status_code == 405:
                    absent = self.client.request("GET", f"/booking/{booking_id}")
                    if absent.status_code == 404:
                        continue
                if response.status_code not in {200, 201, 204, 404}:
                    errors.append(f"{booking_id}: HTTP {response.status_code}")
            except Exception as exc:
                errors.append(f"{booking_id}: {type(exc).__name__}")
        if errors:
            raise RuntimeError("Cleanup failed for owned bookings: " + ", ".join(errors))
