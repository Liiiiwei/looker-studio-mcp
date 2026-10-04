"""Looker Studio 報表 MCP：依客戶與範本組出 Linking API 網址。"""

import functools
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

import url_builder
from registry import Client, RegistryError, load_clients, load_templates, missing_fields
from url_builder import BuildError

mcp = MCPServer("looker-studio")

PREREQUISITES = [
    "該客戶的 Meta 廣告帳戶必須已在 Windsor 連接",
    "開啟網址的 Google 帳號必須有該客戶 Google Ads、GA4 與試算表的存取權",
]
NEXT_STEP = "在已登入的瀏覽器開啟網址，確認預覽數據是該客戶的，再按右上角「編輯及共用」存成新報表"


def _report_errors(fn):
    """把設定檔與客戶資料的錯誤轉成 ToolError，訊息才會原樣傳到 MCP 用戶端。"""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (RegistryError, BuildError, ValueError) as error:
            raise ToolError(str(error)) from error

    return wrapper


def _config_dir() -> Path:
    return Path(os.environ.get("LOOKER_STUDIO_MCP_CONFIG_DIR") or Path(__file__).parent)


def _templates():
    return load_templates(_config_dir() / "templates.yaml")


def _clients():
    return load_clients(_config_dir() / "clients.yaml")


def _pick(items: dict, key: str, label: str):
    if key not in items:
        raise ValueError(f"找不到{label}「{key}」，可用的{label}代號：{'、'.join(items)}")
    return items[key]


def _available(client: Client) -> list[str]:
    """客戶已填齊的資料類型。"""
    available = []
    if client.meta_account_id:
        available.append("meta_windsor")
    if client.google_ads_account_id:
        available.append("google_ads")
    if client.ga4_account_id and client.ga4_property_id:
        available.append("ga4")
    for name, ref in client.sheets.items():
        if ref.spreadsheet_id and ref.worksheet_id:
            available.append(f"sheets.{name}")
    return available


@mcp.tool()
@_report_errors
def list_templates() -> list[dict]:
    """列出可用的 Looker Studio 報表範本：代號、名稱、報表 ID、每個資料來源別名的類型。"""
    result = []
    for template in _templates().values():
        sources = []
        for source in template.sources:
            item = {"alias": source.alias, "type": source.type}
            if source.sheet:
                item["sheet"] = source.sheet
            sources.append(item)
        result.append(
            {
                "key": template.key,
                "name": template.name,
                "report_id": template.report_id,
                "sources": sources,
            }
        )
    return result


@mcp.tool()
@_report_errors
def list_clients() -> list[dict]:
    """列出客戶：代號、名稱、已填齊的資料類型，以及套用每份範本還缺哪些欄位。"""
    templates = _templates()
    return [
        {
            "key": client.key,
            "name": client.name,
            "available": _available(client),
            "missing_by_template": {
                key: missing_fields(client, template) for key, template in templates.items()
            },
        }
        for client in _clients().values()
    ]


@mcp.tool()
@_report_errors
def build_report_url(
    client: str,
    template: str,
    report_name: str | None = None,
    explain: bool = False,
) -> dict:
    """替指定客戶從指定範本組出建立 Looker Studio 報表的網址。

    client 與 template 是代號，可先用 list_clients、list_templates 查。
    report_name 不填時為「客戶名稱-範本名稱」。
    explain 設為 true 時，預覽頁的資訊按鈕會列出每個資料來源的處理方式，用於除錯。
    客戶缺少範本需要的任何帳戶 ID 時會報錯，不會產出網址。
    這個工具只產生網址，不會建立報表；報表要由使用者在瀏覽器按「編輯及共用」才會存下來。
    """
    chosen_template = _pick(_templates(), template, "範本")
    chosen_client = _pick(_clients(), client, "客戶")
    result = url_builder.build_report_url(chosen_client, chosen_template, report_name, explain)
    result["prerequisites"] = PREREQUISITES
    result["next_step"] = NEXT_STEP
    return result


if __name__ == "__main__":
    mcp.run()
