from src.core.erdb import ERDBClient


def test_erdb_builds_url_as_fallback_when_top_posters_is_primary():
    client = ERDBClient({
        "artwork_provider": "top_posters",
        "erdb_token": "Tk-test-token",
        "erdb_base_url": "https://easyratingsdb.com",
        "erdb_posters_enabled": True,
    })
    url = client.build_url("poster", "tt1196946")
    assert url == "https://easyratingsdb.com/Tk-test-token/poster/tt1196946.jpg"
