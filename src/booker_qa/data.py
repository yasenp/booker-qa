from datetime import date, timedelta
from uuid import uuid4


def booking_payload():
    checkin = date.today() + timedelta(days=30)
    return {
        "firstname": "space42-" + uuid4().hex,
        "lastname": "Automation", "totalprice": 123, "depositpaid": True,
        "bookingdates": {"checkin": checkin.isoformat(),
                         "checkout": (checkin + timedelta(days=3)).isoformat()},
        "additionalneeds": "Breakfast",
    }
