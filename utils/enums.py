from enum import Enum


class UserRole(str, Enum):
    employer = "employer"
    worker = "worker"


class OrderStatus(str, Enum):
    pending_offer = "pending_offer"
    assigned = "assigned"
    completed = "completed"
    cancelled = "cancelled"
    no_workers_available = "no_workers_available"


class OfferStatus(str, Enum):
    sent = "sent"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"


class ProfessionRateUnit(str, Enum):
    hour = "hour"
    square_meter = "square_meter"
    window_sash = "window_sash"
