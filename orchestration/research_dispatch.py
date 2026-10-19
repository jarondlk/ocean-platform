"""Explicit local at-least-once queue; never selected as a production fallback."""
from collections import deque


class FakeResearchQueue:
    def __init__(self):
        self.deliveries = deque()
        self.accept_then_fail = False

    def enqueue(self, *, run_id, delivery_id):
        self.deliveries.append({"run_id": run_id, "delivery_id": delivery_id})
        if self.accept_then_fail:
            raise RuntimeError("Synthetic queue acknowledgement lost")

    def deliver_next(self, service):
        delivery = self.deliveries.popleft()
        return service.execute_delivery(**delivery)
