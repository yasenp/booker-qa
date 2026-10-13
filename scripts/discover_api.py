"""One-off capability probe; deletes only IDs created by this invocation."""
import json
import uuid

import httpx

BASE = "https://restful-booker.herokuapp.com"
payload = {
    "firstname": "qa-discovery-" + uuid.uuid4().hex[:10],
    "lastname": "Space42", "totalprice": 123, "depositpaid": True,
    "bookingdates": {"checkin": "2027-01-10", "checkout": "2027-01-12"},
    "additionalneeds": "Discovery",
}
ids = []
results = {}
with httpx.Client(base_url=BASE, timeout=30, headers={"Accept": "application/json"}) as client:
    auth = client.post("/auth", json={"username": "admin", "password": "password123"})
    auth.raise_for_status()
    token = auth.json()["token"]
    headers = {"Cookie": "token=" + token}
    results["auth"] = {"status": auth.status_code, "has_token": bool(token)}
    try:
        for label, body in [("create", payload), ("duplicate", payload),
                            ("reversed_dates", {**payload, "bookingdates": {"checkin": "2027-01-12", "checkout": "2027-01-10"}}),
                            ("negative_price", {**payload, "totalprice": -1})]:
            # Separate client context for duplicate; same public account model.
            with httpx.Client(base_url=BASE, timeout=30) as context:
                response = context.post("/booking", json=body)
            entry = {"status": response.status_code}
            try:
                data = response.json()
                if "bookingid" in data:
                    ids.append(data["bookingid"])
                entry["body"] = data
            except ValueError:
                entry["body"] = response.text
            results[label] = entry
        booking_id = ids[0]
        results["invalid_token_put"] = client.put(f"/booking/{booking_id}", json=payload, headers={"Cookie": "token=invalid"}).status_code
        results["put_statuses"] = [client.put(f"/booking/{booking_id}", json=payload, headers=headers).status_code for _ in range(3)]
        results["patch_status"] = client.patch(f"/booking/{booking_id}", json={"totalprice": 456}, headers=headers).status_code
        final = client.get(f"/booking/{booking_id}")
        results["final_get"] = {"status": final.status_code, "body": final.json()}
        results["missing_get"] = client.get("/booking/2147483647").status_code
    finally:
        results["cleanup"] = {str(i): client.delete(f"/booking/{i}", headers=headers).status_code for i in ids}
        print(json.dumps(results, indent=2))
