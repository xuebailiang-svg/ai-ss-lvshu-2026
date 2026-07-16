from __future__ import annotations

from enum import Enum


class DataSourceType(str, Enum):
    amap = "amap"
    crawler = "crawler"
    manual = "manual"
    user_upload = "user_upload"
    third_party = "third_party"


class DataStatus(str, Enum):
    confirmed = "confirmed"
    estimated = "estimated"
    missing = "missing"
    pending_review = "pending_review"
    rejected = "rejected"


class POICategory(str, Enum):
    transport = "transport"
    competitor = "competitor"
    food = "food"
    entertainment = "entertainment"
    education = "education"
    residential = "residential"
    commercial = "commercial"
    sensitive = "sensitive"
    other = "other"


class EntertainmentType(str, Enum):
    ktv = "ktv"
    bar = "bar"
    billiard = "billiard"
    cinema = "cinema"
    escape_room = "escape_room"
    other = "other"
