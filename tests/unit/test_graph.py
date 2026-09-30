import httpx
import pytest
import respx

from teamsleech.services.auth import TokenExpiredError
from teamsleech.services.graph import GraphAPIError, GraphClient


class TestGraphClient:
    async def test_get_success(self, graph_client: GraphClient, mock_graph_api):
        mock_graph_api.get("/me").respond(200, json={"id": "user1"})
        result = await graph_client.get("/me")
        assert result == {"id": "user1"}

    async def test_get_with_params(self, graph_client: GraphClient, mock_graph_api):
        mock_graph_api.get("/users").respond(200, json={"value": [{"id": "u1"}]})
        result = await graph_client.get("/users", params={"$top": "10"})
        assert result == {"value": [{"id": "u1"}]}

    async def test_get_unauthorized_raises_token_expired(
        self, graph_client: GraphClient, mock_graph_api
    ):
        mock_graph_api.get("/me").respond(401, text="Unauthorized")
        with pytest.raises(TokenExpiredError, match="401"):
            await graph_client.get("/me")

    async def test_get_http_error_truncates_body(self, graph_client: GraphClient, mock_graph_api):
        long_body = "x" * 500
        mock_graph_api.get("/me").respond(500, text=long_body)
        with pytest.raises(GraphAPIError) as exc:
            await graph_client.get("/me")
        assert len(str(exc.value)) < 400

    async def test_get_network_error(self, graph_client: GraphClient):
        with respx.mock(base_url="https://graph.microsoft.com/v1.0") as mock:
            mock.get("/me").mock(side_effect=httpx.RequestError("Connection refused"))
            with pytest.raises(GraphAPIError, match="Network error"):
                await graph_client.get("/me")

    async def test_get_rejects_non_graph_url(self, graph_client: GraphClient):
        with pytest.raises(GraphAPIError, match="non-Graph"):
            await graph_client.get("https://other.api.com/endpoint")

    async def test_get_graph_absolute_url(self, graph_client: GraphClient, mock_graph_api):
        mock_graph_api.get("/endpoint").respond(200, json={"ok": True})
        result = await graph_client.get("https://graph.microsoft.com/v1.0/endpoint")
        assert result == {"ok": True}

    async def test_quote_id(self):
        from teamsleech.services.graph import quote_id

        assert quote_id("b!abcXYZ") == "b!abcXYZ"
        assert quote_id("a'b\"c") == "a%27b%22c"

    async def test_post_success(self, graph_client: GraphClient, mock_graph_api):
        mock_graph_api.post("/items").respond(201, json={"id": "new_item"})
        result = await graph_client.post("/items", json_data={"name": "test"})
        assert result == {"id": "new_item"}

    async def test_post_no_content(self, graph_client: GraphClient, mock_graph_api):
        mock_graph_api.post("/items").respond(204)
        result = await graph_client.post("/items", json_data={"name": "test"})
        assert result == {}

    async def test_post_http_error(self, graph_client: GraphClient, mock_graph_api):
        mock_graph_api.post("/items").respond(400, text="Bad request")
        with pytest.raises(GraphAPIError, match="400"):
            await graph_client.post("/items", json_data={})

    async def test_post_network_error(self, graph_client: GraphClient):
        with respx.mock(base_url="https://graph.microsoft.com/v1.0") as mock:
            mock.post("/items").mock(side_effect=httpx.RequestError("Timeout"))
            with pytest.raises(GraphAPIError, match="Network error"):
                await graph_client.post("/items", json_data={})

    async def test_get_all_pages_single(self, graph_client: GraphClient, mock_graph_api):
        mock_graph_api.get("/users").respond(
            200, json={"value": [{"id": "u1"}], "@odata.nextLink": None}
        )
        results = await graph_client.get_all_pages("/users")
        assert results == [{"id": "u1"}]

    async def test_get_all_pages_multi(self, graph_client: GraphClient, mock_graph_api):
        mock_graph_api.get("/users?$skip=1").respond(200, json={"value": [{"id": "u2"}]})
        mock_graph_api.get("/users").respond(
            200,
            json={
                "value": [{"id": "u1"}],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?$skip=1",
            },
        )
        results = await graph_client.get_all_pages("/users")
        assert results == [{"id": "u1"}, {"id": "u2"}]

    async def test_get_all_pages_absolute_url(self, graph_client: GraphClient, mock_graph_api):
        mock_graph_api.get("/users?$top=1&$skip=1").respond(200, json={"value": [{"id": "u2"}]})
        mock_graph_api.get("/users").respond(
            200,
            json={
                "value": [{"id": "u1"}],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?$top=1&$skip=1",
            },
        )
        results = await graph_client.get_all_pages("https://graph.microsoft.com/v1.0/users?$top=1")
        assert results == [{"id": "u1"}, {"id": "u2"}]

    async def test_get_all_pages_infinite_loop_guard(
        self, graph_client: GraphClient, mock_graph_api
    ):
        loop_link = "https://graph.microsoft.com/v1.0/users?$skip=1"
        mock_graph_api.get("/users?$skip=1").respond(
            200,
            json={
                "value": [{"id": "u1"}],
                "@odata.nextLink": loop_link,
            },
        )
        mock_graph_api.get("/users").respond(
            200,
            json={
                "value": [{"id": "u1"}],
                "@odata.nextLink": loop_link,
            },
        )
        results = await graph_client.get_all_pages("/users")
        assert results == [{"id": "u1"}, {"id": "u1"}]

    async def test_get_retries_throttled_then_succeeds(
        self, graph_client: GraphClient, mock_graph_api
    ):
        route = mock_graph_api.get("/me")
        route.side_effect = [
            httpx.Response(429, text="throttled"),
            httpx.Response(200, json={"id": "user1"}),
        ]
        result = await graph_client.get("/me")
        assert result == {"id": "user1"}
        assert route.call_count == 2

    async def test_get_all_pages_forwards_params(self, graph_client: GraphClient, mock_graph_api):
        route = mock_graph_api.get("/users", params={"$top": "1"})
        route.respond(200, json={"value": [{"id": "u1"}]})
        results = await graph_client.get_all_pages("/users", params={"$top": "1"})
        assert results == [{"id": "u1"}]
        assert route.called

    async def test_get_all_pages_caps_runaway_pagination(
        self, graph_client: GraphClient, mock_graph_api
    ):
        mock_graph_api.get("/users?$skip=2").respond(200, json={"value": [{"id": "u3"}]})
        mock_graph_api.get("/users?$skip=1").respond(
            200,
            json={
                "value": [{"id": "u2"}],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?$skip=2",
            },
        )
        mock_graph_api.get("/users").respond(
            200,
            json={
                "value": [{"id": "u1"}],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?$skip=1",
            },
        )
        results = await graph_client.get_all_pages("/users", max_pages=2)
        assert results == [{"id": "u1"}, {"id": "u2"}]

    async def test_close(self, graph_client: GraphClient):
        await graph_client.close()

    async def test_async_context_manager(self):
        async with GraphClient(access_token="t") as client:
            assert client.access_token == "t"
