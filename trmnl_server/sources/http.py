"""Shared httpx client for the adapters that just GET JSON off the LAN."""
import httpx

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=10.0, headers={"X-Client-Name": "trmnl-server"})
    return _client


async def close():
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def get_json(url: str) -> dict:
    response = await client().get(url)
    response.raise_for_status()
    return response.json()
