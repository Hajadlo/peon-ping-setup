"""When a T3 main-thread status change deserves an alert: delays, dedup, retries."""
import hashlib
import json
import sqlite3
import urllib.error

ALERTS = {
    "completed": "Done",
    "input": "Needs input",
    "approval": "Needs approval",
    "failed": "Needs attention",
}
# Seconds a status must hold before it alerts; filters short-lived flickers.
DELAYS = {"completed": 5, "input": 2, "approval": 2, "failed": 15}


def transition_key(key):
    phase, turn, approvals, inputs = key[:4]
    if phase in ("input", "approval", "failed"):
        # Counts and turn IDs can change while the same request remains open.
        return [phase, None, 0, 0]
    return [phase, turn, int(bool(approvals)), int(bool(inputs))]


def baseline(current, now):
    """Treat statuses that exist at first start as already announced."""
    return {
        thread: {"key": transition_key(key), "since": now, "sent": True,
                 "completed_turn": key[1] if key[0] == "completed" else None,
                 "completed_request": key[4] if key[0] == "completed" and len(key) > 4 else None}
        for thread, key in current.items()
    }


def sequence_id(value):
    return hashlib.sha256(value.encode()).hexdigest()


def advance(records, current, now, send, *, confirm_completion):
    for thread in records.keys() - current.keys():
        del records[thread]
    for thread, key in current.items():
        phase, turn, *_ = key
        request = key[4] if len(key) > 4 else None
        key = transition_key(key)
        record = records.setdefault(thread, {"completed_turn": None})
        if record.get("key") != key:
            record.update(key=key, since=now, sent=False, retry_at=0)
        if phase not in ALERTS or record["sent"]:
            continue
        # One Done per human request: automatic follow-up runs do not repeat it.
        if phase == "completed" and (record["completed_turn"] == turn or
                                     (request and record.get("completed_request") == request)):
            continue
        if now < record.get("retry_at", 0) or now - record["since"] < DELAYS[phase]:
            continue
        if phase == "completed" and not confirm_completion(thread, turn, now):
            continue
        new_id = sequence_id(json.dumps([thread, key, record["since"]]))
        try:
            send(phase, thread, record.get("notification_id", sequence_id(thread)), new_id)
        except (OSError, urllib.error.URLError, sqlite3.Error) as error:
            print(f"Delivery failed ({type(error).__name__}); retrying in 30s", flush=True)
            record["retry_at"] = now + 30
            continue
        record["sent"] = True
        record["notification_id"] = new_id
        if phase == "completed":
            record["completed_turn"] = turn
            record["completed_request"] = request
        print(f"Sent {phase} sound thread={thread} turn={turn}", flush=True)


def save(path, records):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(records))
    temporary.replace(path)
