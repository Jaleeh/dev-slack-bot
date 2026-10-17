import threading

from fastapi.testclient import TestClient

from tests.integration.freezable_proxy import FreezableProxy
from tests.support import UNREACHABLE_DATABASE_URL, ClientFactory

HANG_LIMIT_SECONDS = 5


def test_health_reports_database_ok_when_postgres_is_up(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_database_down_when_unreachable(
    client_for_database: ClientFactory,
) -> None:
    client = client_for_database(UNREACHABLE_DATABASE_URL)

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "down"}


def test_health_returns_quickly_when_database_hangs(
    client_for_database: ClientFactory, test_database_url: str
) -> None:
    with FreezableProxy(test_database_url) as proxy:
        proxy.freeze()
        client = client_for_database(proxy.url)

        status_code = get_status_within(client, "/api/health", HANG_LIMIT_SECONDS)

    assert status_code == 503


def test_health_returns_quickly_when_database_freezes_after_a_good_check(
    client_for_database: ClientFactory, test_database_url: str
) -> None:
    with FreezableProxy(test_database_url) as proxy:
        client = client_for_database(proxy.url)
        assert client.get("/api/health").status_code == 200

        proxy.freeze()
        status_code = get_status_within(client, "/api/health", HANG_LIMIT_SECONDS)

    assert status_code == 503


def test_health_returns_quickly_when_database_stalls_mid_query(
    client_for_database: ClientFactory, test_database_url: str
) -> None:
    with FreezableProxy(test_database_url) as proxy:
        proxy.freeze_on_next_query()
        client = client_for_database(proxy.url)

        status_code = get_status_within(client, "/api/health", HANG_LIMIT_SECONDS)

    assert status_code == 503


def get_status_within(client: TestClient, path: str, seconds: float) -> int | str:
    """Status code of GET path, or "hung" if it takes longer than seconds."""
    status_codes: list[int] = []
    # Daemon, so a hung request cannot keep pytest from exiting.
    worker = threading.Thread(
        target=lambda: status_codes.append(client.get(path).status_code), daemon=True
    )
    worker.start()
    worker.join(seconds)
    return status_codes[0] if status_codes else "hung"
