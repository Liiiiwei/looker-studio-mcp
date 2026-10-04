import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import server

TEMPLATES = """\
templates:
  ecommerce:
    name: 電商成效報表
    report_id: rid-1
    sources:
      ds8: { type: meta_windsor }
      ds25: { type: google_ads }
      ds0: { type: ga4 }
      ds119: { type: sheets, sheet: budget }
  ga_only:
    name: 流量報表
    report_id: rid-2
    sources:
      ds0: { type: ga4 }
"""

CLIENTS = """\
clients:
  happyhabit:
    name: 每日衡好
    meta_account_id: "1234567890123456"
    google_ads_account_id: "1234567890"
    ga4: { account_id: "111", property_id: "222" }
    sheets:
      budget: { spreadsheet_id: "1AbC", worksheet_id: "0" }
  newbie:
    name: 新客戶
    meta_account_id: "999"
"""


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    (tmp_path / "templates.yaml").write_text(TEMPLATES, encoding="utf-8")
    (tmp_path / "clients.yaml").write_text(CLIENTS, encoding="utf-8")
    monkeypatch.setenv("LOOKER_STUDIO_MCP_CONFIG_DIR", str(tmp_path))
    return tmp_path


def test_list_templates(config_dir):
    assert server.list_templates() == [
        {
            "key": "ecommerce",
            "name": "電商成效報表",
            "report_id": "rid-1",
            "sources": [
                {"alias": "ds8", "type": "meta_windsor"},
                {"alias": "ds25", "type": "google_ads"},
                {"alias": "ds0", "type": "ga4"},
                {"alias": "ds119", "type": "sheets", "sheet": "budget"},
            ],
        },
        {
            "key": "ga_only",
            "name": "流量報表",
            "report_id": "rid-2",
            "sources": [{"alias": "ds0", "type": "ga4"}],
        },
    ]


def test_list_clients(config_dir):
    assert server.list_clients() == [
        {
            "key": "happyhabit",
            "name": "每日衡好",
            "available": ["meta_windsor", "google_ads", "ga4", "sheets.budget"],
            "missing_by_template": {"ecommerce": [], "ga_only": []},
        },
        {
            "key": "newbie",
            "name": "新客戶",
            "available": ["meta_windsor"],
            "missing_by_template": {
                "ecommerce": [
                    "google_ads_account_id",
                    "ga4.account_id",
                    "ga4.property_id",
                    "sheets.budget.spreadsheet_id",
                    "sheets.budget.worksheet_id",
                ],
                "ga_only": ["ga4.account_id", "ga4.property_id"],
            },
        },
    ]


def test_build_report_url(config_dir):
    result = server.build_report_url("happyhabit", "ecommerce")

    assert result["url"].startswith("https://lookerstudio.google.com/reporting/create?c.reportId=rid-1&")
    assert result["report_name"] == "每日衡好-電商成效報表"
    assert [item["alias"] for item in result["replacements"]] == ["ds8", "ds25", "ds0", "ds119"]
    assert result["prerequisites"] == server.PREREQUISITES
    assert result["next_step"] == server.NEXT_STEP


def test_build_report_url_passes_options(config_dir):
    result = server.build_report_url("happyhabit", "ga_only", report_name="十月流量", explain=True)

    assert "c.explain=true" in result["url"]
    assert result["report_name"] == "十月流量"


def test_unknown_client_lists_valid_keys(config_dir):
    with pytest.raises(ToolError) as error:
        server.build_report_url("nobody", "ecommerce")
    assert "找不到客戶「nobody」" in str(error.value)
    assert "happyhabit" in str(error.value) and "newbie" in str(error.value)


def test_unknown_template_lists_valid_keys(config_dir):
    with pytest.raises(ToolError) as error:
        server.build_report_url("happyhabit", "nope")
    assert "找不到範本「nope」" in str(error.value)
    assert "ecommerce" in str(error.value) and "ga_only" in str(error.value)


def test_incomplete_client_raises(config_dir):
    with pytest.raises(ToolError, match="客戶「newbie」缺少範本「ecommerce」需要的欄位"):
        server.build_report_url("newbie", "ecommerce")


def test_yaml_edits_take_effect_without_restart(config_dir):
    assert len(server.list_templates()) == 2
    (config_dir / "templates.yaml").write_text(
        "templates:\n  only:\n    report_id: r\n    sources:\n      ds0: { type: ga4 }\n",
        encoding="utf-8",
    )
    assert [item["key"] for item in server.list_templates()] == ["only"]


def test_missing_config_file_is_reported_as_tool_error(config_dir):
    (config_dir / "clients.yaml").unlink()
    with pytest.raises(ToolError, match="clients.example.yaml"):
        server.list_clients()


def test_error_message_reaches_mcp_client(config_dir):
    """經過 MCP 的工具呼叫層後，使用者仍要看得到缺哪些欄位。"""
    with pytest.raises(Exception) as error:
        asyncio.run(server.mcp.call_tool("build_report_url", {"client": "newbie", "template": "ecommerce"}))
    assert "客戶「newbie」缺少範本「ecommerce」需要的欄位" in str(error.value)
    assert "google_ads_account_id" in str(error.value)
