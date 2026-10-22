"""Session isolation tests — strangers sharing one deployed database must
never see each other's logs.

Design (see app/deps.py): every browser gets a random X-Session-Id header;
uploads are tagged with it; every read endpoint returns the caller only their
OWN rows plus the SHARED anonymous bucket (owner == "", where headerless curl
uploads / SEED_ON_START data live). Trace drawer flows through GET /api/logs,
so scoping the search endpoint closes the trace leak too.
"""

import io

ALICE = {"X-Session-Id": "sess-alice-0001"}
BOB = {"X-Session-Id": "sess-bob-0002"}

ALICE_LINE = (
    '{"timestamp": "2026-10-21T10:00:00Z", "severity": "ERROR", '
    '"service": "alice-api", "request_id": "req-alice-1", '
    '"message": "alice exploded three times in a row"}\n'
    '{"timestamp": "2026-10-21T10:01:00Z", "severity": "ERROR", '
    '"service": "alice-api", "request_id": "req-alice-2", '
    '"message": "alice exploded three times in a row"}\n'
    '{"timestamp": "2026-10-21T10:02:00Z", "severity": "CRITICAL", '
    '"service": "alice-api", "request_id": "req-alice-3", '
    '"message": "alice exploded three times in a row"}\n'
)
BOB_LINE = (
    '{"timestamp": "2026-10-21T11:00:00Z", "severity": "INFO", '
    '"service": "bob-web", "request_id": "req-bob-1", '
    '"message": "bob is fine"}\n'
)


def _upload(client, content: str, headers: dict, filename: str = "session.log"):
    return client.post(
        "/api/logs/upload",
        files={"file": (filename, io.BytesIO(content.encode("utf-8")), "text/plain")},
        headers=headers,
    )


def test_upload_not_visible_to_other_sessions(client):
    """One visitor's upload must never appear in another visitor's view."""
    res = _upload(client, BOB_LINE, ALICE)
    assert res.status_code == 200
    assert res.json()["parsed_lines"] == 1

    # Owner sees it
    mine = client.get("/api/logs", headers=ALICE)
    assert mine.json()["total"] == 1
    assert mine.json()["entries"][0]["service"] == "bob-web"

    # A different session does NOT
    other = client.get("/api/logs", headers=BOB)
    assert other.json()["total"] == 0

    # And neither do headerless visitors (they live in the anonymous bucket)
    anon = client.get("/api/logs")
    assert anon.json()["total"] == 0


def test_two_sessions_fully_isolated_across_uploads(client):
    """Both sessions upload; each sees exactly their own rows."""
    _upload(client, ALICE_LINE, ALICE)
    _upload(client, BOB_LINE, BOB)

    a = client.get("/api/logs", headers=ALICE).json()
    b = client.get("/api/logs", headers=BOB).json()
    assert a["total"] == 3 and {e["service"] for e in a["entries"]} == {"alice-api"}
    assert b["total"] == 1 and {e["service"] for e in b["entries"]} == {"bob-web"}


def test_summary_and_timeline_scoped_per_session(client):
    """The stats cards / activity chart must never aggregate strangers' logs."""
    _upload(client, ALICE_LINE, ALICE)
    _upload(client, BOB_LINE, BOB)

    a_sum = client.get("/api/stats/summary", headers=ALICE).json()
    b_sum = client.get("/api/stats/summary", headers=BOB).json()
    assert a_sum["total_entries"] == 3
    assert a_sum["by_service"] == {"alice-api": 3}
    assert b_sum["total_entries"] == 1
    assert b_sum["by_service"] == {"bob-web": 1}

    a_tl = client.get("/api/stats/timeline?bucket=hour", headers=ALICE).json()
    bob_svcs_total = sum(
        sum(v for k, v in bucket.items() if k != "start") for bucket in a_tl["buckets"]
    )
    assert bob_svcs_total == 3  # alice's chart contains only alice's volume


def test_trace_request_id_scoped_per_session(client):
    """The trace drawer (search by request_id) must not leak across sessions."""
    _upload(client, ALICE_LINE, ALICE)

    mine = client.get("/api/logs?request_id=req-alice-1", headers=ALICE).json()
    theirs = client.get("/api/logs?request_id=req-alice-1", headers=BOB).json()
    assert mine["total"] == 1
    assert theirs["total"] == 0  # same request id, invisible to bob


def test_streaks_scoped_per_session(client):
    """Streak alerts must fire only for the session whose data is failing."""
    _upload(client, ALICE_LINE, ALICE)  # alice is on a 3-entry error streak
    _upload(client, BOB_LINE, BOB)

    a = client.get("/api/stats/streaks?min=3", headers=ALICE).json()
    b = client.get("/api/stats/streaks?min=3", headers=BOB).json()
    assert len(a["streaks"]) == 1 and a["streaks"][0]["service"] == "alice-api"
    assert b["streaks"] == []  # bob has no data on fire — no false alarm


def test_health_counter_scoped_per_session(client):
    """The header pill shows MY entry count, not everyone else's combined."""
    _upload(client, ALICE_LINE, ALICE)
    _upload(client, BOB_LINE, BOB)

    a = client.get("/api/health", headers=ALICE).json()
    b = client.get("/api/health", headers=BOB).json()
    anon = client.get("/api/health").json()
    assert a["total_entries"] == 3
    assert b["total_entries"] == 1
    assert anon["total_entries"] == 0


def test_anonymous_bucket_is_shared_baseline(client):
    """Rows with owner == "" (seeded data, headerless curl uploads) are the
    deliberately shared layer: visible to sessions AND headerless callers."""
    _upload(client, BOB_LINE, {}, filename="anon.log")  # no X-Session-Id → owner ""

    a = client.get("/api/logs", headers=ALICE).json()
    anon = client.get("/api/logs").json()
    assert a["total"] == 1 and a["entries"][0]["service"] == "bob-web"
    assert anon["total"] == 1
