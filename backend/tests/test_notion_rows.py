"""
Notion bulk-row support — the fix for "Created successfully." over an EMPTY database.

Root cause being locked in here: the chat loop ends at the first confirm-gated write
action, so a plan of create_database + N create_page calls could never insert rows.
Rows must therefore ride INSIDE the single confirmed call (create_database rows=... /
create_pages), and confirmations must report honest row accounting.
"""
import json
import unittest
from unittest.mock import AsyncMock, patch

from backend.lib.business.connectors.notion_conn import NotionConnector
from backend.lib.business.tool_builder import _TOOLS
from backend.routes.business.chat import (
    WRITE_ACTIONS,
    _describe_action,
    _make_fallback_confirmation,
)


def _connector() -> NotionConnector:
    return NotionConnector(credentials={"api_key": "ntn_test"})


class TestPropPayload(unittest.TestCase):
    """Flat value → Notion property payload conversion."""

    def test_title_and_rich_text(self):
        self.assertEqual(
            NotionConnector._prop_payload("title", "Mario's Garage"),
            {"title": [{"type": "text", "text": {"content": "Mario's Garage"}}]},
        )
        self.assertEqual(
            NotionConnector._prop_payload("rich_text", "pitch text"),
            {"rich_text": [{"type": "text", "text": {"content": "pitch text"}}]},
        )

    def test_number_coercion(self):
        self.assertEqual(NotionConnector._prop_payload("number", 80), {"number": 80.0})
        self.assertEqual(NotionConnector._prop_payload("number", "1,332"), {"number": 1332.0})
        self.assertEqual(NotionConnector._prop_payload("number", "$4.8"), {"number": 4.8})
        self.assertIsNone(NotionConnector._prop_payload("number", "not a number"))

    def test_url_phone_email_select(self):
        self.assertEqual(
            NotionConnector._prop_payload("url", "https://maps.google.com/?q=1,2"),
            {"url": "https://maps.google.com/?q=1,2"},
        )
        self.assertEqual(
            NotionConnector._prop_payload("phone_number", "(416) 531-0875"),
            {"phone_number": "(416) 531-0875"},
        )
        self.assertEqual(NotionConnector._prop_payload("email", "a@b.co"), {"email": "a@b.co"})
        self.assertEqual(NotionConnector._prop_payload("select", "Roofing"), {"select": {"name": "Roofing"}})

    def test_checkbox_strings(self):
        self.assertEqual(NotionConnector._prop_payload("checkbox", "yes"), {"checkbox": True})
        self.assertEqual(NotionConnector._prop_payload("checkbox", "false"), {"checkbox": False})
        self.assertEqual(NotionConnector._prop_payload("checkbox", True), {"checkbox": True})

    def test_empty_values_skipped(self):
        self.assertIsNone(NotionConnector._prop_payload("rich_text", ""))
        self.assertIsNone(NotionConnector._prop_payload("rich_text", None))
        self.assertIsNone(NotionConnector._prop_payload("rich_text", "   "))

    def test_unsupported_type_skipped(self):
        self.assertIsNone(NotionConnector._prop_payload("formula", "x"))


class TestRowToProperties(unittest.TestCase):
    def test_case_insensitive_column_match(self):
        conn = _connector()
        schema = {"Name": "title", "Phone": "phone_number", "Score": "number"}
        props, skipped = conn._row_to_properties(schema, {"name": "A", "PHONE": "(1)", "score": 3, "Bogus": "x"})
        self.assertIn("Name", props)
        self.assertIn("Phone", props)
        self.assertIn("Score", props)
        self.assertEqual(skipped, ["Bogus"])

    def test_all_unmatched_returns_empty(self):
        conn = _connector()
        props, skipped = conn._row_to_properties({"Name": "title"}, {"Foo": "x"})
        self.assertEqual(props, {})
        self.assertEqual(skipped, ["Foo"])


class TestCreateDatabaseWithRows(unittest.IsolatedAsyncioTestCase):
    async def test_rows_inserted_in_same_call(self):
        conn = _connector()

        class FakeResp:
            def __init__(self, payload, status=200):
                self._payload = payload
                self.status_code = status

            def json(self):
                return self._payload

            def raise_for_status(self):
                pass

        db_resp = FakeResp({"id": "db_1", "url": "https://notion.so/db_1"})
        page_resp = FakeResp({"id": "pg", "url": "u"})
        post_mock = AsyncMock(side_effect=[db_resp, page_resp, page_resp])

        with patch("backend.lib.business.connectors.notion_conn.httpx.AsyncClient") as client_cls, \
             patch("backend.lib.business.connectors.notion_conn.asyncio.sleep", new=AsyncMock()):
            client = client_cls.return_value.__aenter__.return_value
            client.post = post_mock
            result = await conn.create_database(
                parent_page_id="parent_1",
                title="HOT Call List",
                columns=[{"name": "Phone", "type": "phone_number"}, {"name": "Score", "type": "number"}],
                rows=[
                    {"Name": "Mario's Garage", "Phone": "(416) 531-0875", "Score": 80},
                    {"Name": "topplusroofing", "Phone": "(647) 213-1121", "Score": 56},
                ],
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.data["database_id"], "db_1")
        self.assertEqual(result.data["rows_created"], 2)
        self.assertEqual(result.data["rows_failed"], 0)
        # 1 database create + 2 row inserts, all inside the one confirmed action
        self.assertEqual(post_mock.await_count, 3)
        row_body = post_mock.await_args_list[1].kwargs["json"]
        self.assertEqual(row_body["parent"], {"database_id": "db_1"})
        self.assertIn("Name", row_body["properties"])
        self.assertIn("Phone", row_body["properties"])

    async def test_failed_rows_are_reported_not_hidden(self):
        conn = _connector()

        class FakeResp:
            def __init__(self, payload, status=200):
                self._payload = payload
                self.status_code = status

            def json(self):
                return self._payload

            def raise_for_status(self):
                pass

        db_resp = FakeResp({"id": "db_1", "url": "https://notion.so/db_1"})
        bad_resp = FakeResp({"message": "validation error"}, status=400)
        post_mock = AsyncMock(side_effect=[db_resp, bad_resp])

        with patch("backend.lib.business.connectors.notion_conn.httpx.AsyncClient") as client_cls, \
             patch("backend.lib.business.connectors.notion_conn.asyncio.sleep", new=AsyncMock()):
            client = client_cls.return_value.__aenter__.return_value
            client.post = post_mock
            result = await conn.create_database(
                parent_page_id="p", title="T",
                columns=[], rows=[{"Name": "X"}],
            )

        self.assertTrue(result.ok)  # DB itself exists
        self.assertEqual(result.data["rows_created"], 0)
        self.assertEqual(result.data["rows_failed"], 1)
        self.assertIn("validation error", result.data["failures"][0]["error"])


class TestBulkInsertExistingDb(unittest.IsolatedAsyncioTestCase):
    async def test_zero_inserts_is_an_error(self):
        conn = _connector()

        class FakeResp:
            def __init__(self, payload, status=200):
                self._payload = payload
                self.status_code = status

            def json(self):
                return self._payload

            def raise_for_status(self):
                pass

        db_get = FakeResp({"url": "u", "properties": {"Name": {"type": "title"}}})

        with patch("backend.lib.business.connectors.notion_conn.httpx.AsyncClient") as client_cls, \
             patch("backend.lib.business.connectors.notion_conn.asyncio.sleep", new=AsyncMock()):
            client = client_cls.return_value.__aenter__.return_value
            client.get = AsyncMock(return_value=db_get)
            client.post = AsyncMock(return_value=FakeResp({"message": "boom"}, status=400))
            result = await conn.create_pages_bulk("db_1", [{"Name": "X"}])

        self.assertFalse(result.ok)
        self.assertIn("0 of 1", result.error)

    async def test_rows_required(self):
        conn = _connector()
        result = await conn.create_pages_bulk("db_1", [])
        self.assertFalse(result.ok)


class TestChatWiring(unittest.TestCase):
    def test_create_pages_is_confirm_gated(self):
        self.assertIn("notion__create_pages", WRITE_ACTIONS)

    def test_tool_is_registered(self):
        self.assertIn("notion__create_pages", _TOOLS)
        self.assertIn("rows", _TOOLS["notion__create_database"]["input_schema"]["properties"])

    def test_describe_action_row_counts(self):
        self.assertEqual(
            _describe_action("notion__create_pages", {"rows": [{}, {}, {}]}),
            "Add 3 rows to Notion database",
        )
        self.assertEqual(
            _describe_action("notion__create_database", {"title": "Leads", "rows": [{}, {}]}),
            "Create Notion database: Leads (2 rows)",
        )
        self.assertEqual(
            _describe_action("notion__create_database", {"title": "Leads"}),
            "Create Notion database: Leads",
        )

    def test_confirmation_reports_rows(self):
        msg = _make_fallback_confirmation("notion__create_database", {
            "status": "created", "title": "HOT Call List",
            "database_id": "db_1", "url": "https://notion.so/db_1",
            "rows_created": 10, "rows_failed": 0,
        })
        self.assertIn("10 rows inserted", msg)
        self.assertIn("https://notion.so/db_1", msg)
        self.assertNotEqual(msg, "Created successfully.")

    def test_confirmation_surfaces_failures(self):
        msg = _make_fallback_confirmation("notion__create_database", {
            "status": "created", "title": "T", "database_id": "d",
            "rows_created": 7, "rows_failed": 3,
            "failures": [{"row": 2, "error": "validation error"}],
        })
        self.assertIn("7 rows inserted", msg)
        self.assertIn("3 FAILED", msg)
        self.assertIn("validation error", msg)


if __name__ == "__main__":
    unittest.main()
