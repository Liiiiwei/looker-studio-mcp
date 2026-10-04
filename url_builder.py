"""把客戶與範本組成 Looker Studio Linking API 網址。不碰檔案、不碰網路。"""

from __future__ import annotations

import re
from urllib.parse import quote, urlencode

from registry import Client, Source, Template, missing_fields

BASE_URL = "https://lookerstudio.google.com/reporting/create"
# Windsor.ai 的 Looker Studio 連接器部署 ID，所有 Windsor 資料來源共用
WINDSOR_CONNECTOR_ID = "AKfycbwMs3jUvu_RtMs6XtlspAdiMR8X19N1DAi8mYOCfUxy6I3NHhXRR9qkqxg83fG2js71"

TYPE_LABELS = {
    "meta_windsor": "Meta 廣告",
    "google_ads": "Google Ads",
    "ga4": "GA4",
    "sheets": "試算表",
}


class BuildError(Exception):
    """客戶資料不足或 ID 格式錯誤，無法組出網址。"""


def _digits(value: str, label: str) -> str:
    if not re.fullmatch(r"\d+", value):
        raise BuildError(f"{label} 必須是純數字，目前是「{value}」")
    return value


def _connection(source: Source, client: Client) -> tuple[list[tuple[str, str]], str]:
    """回傳（這個來源的連線參數, 給人看的替換目標）。"""
    if source.type == "meta_windsor":
        account = _digits(client.meta_account_id.removeprefix("act_"), "meta_account_id")
        selector = f"facebook__{account}"
        return [
            ("connector", "community"),
            ("connectorId", WINDSOR_CONNECTOR_ID),
            ("configuredAccountsSelector", selector),
        ], selector

    if source.type == "google_ads":
        account = re.sub(r"[-\s]", "", client.google_ads_account_id)
        if not re.fullmatch(r"\d{10}", account):
            raise BuildError(
                f"google_ads_account_id 去掉連字號後必須是 10 碼數字，目前是「{client.google_ads_account_id}」"
            )
        return [("connector", "googleAds"), ("accountId", account)], account

    if source.type == "ga4":
        account = _digits(client.ga4_account_id, "ga4.account_id")
        prop = _digits(client.ga4_property_id, "ga4.property_id")
        return [
            ("connector", "googleAnalytics"),
            ("accountId", account),
            ("propertyId", prop),
        ], f"{account}/{prop}"

    ref = client.sheets[source.sheet]
    worksheet = _digits(ref.worksheet_id, f"sheets.{source.sheet}.worksheet_id")
    return [
        ("connector", "googleSheets"),
        ("spreadsheetId", ref.spreadsheet_id),
        ("worksheetId", worksheet),
    ], f"{ref.spreadsheet_id}#{worksheet}"


def build_report_url(
    client: Client,
    template: Template,
    report_name: str | None = None,
    explain: bool = False,
) -> dict:
    missing = missing_fields(client, template)
    if missing:
        raise BuildError(
            f"客戶「{client.key}」缺少範本「{template.key}」需要的欄位：{'、'.join(missing)}"
        )

    name = (report_name or "").strip() or f"{client.name}-{template.name}"
    params: list[tuple[str, str]] = [("c.reportId", template.report_id)]
    if explain:
        params.append(("c.explain", "true"))
    params.append(("r.reportName", name))

    errors: list[str] = []
    replacements: list[dict] = []
    for source in template.sources:
        try:
            connection, target = _connection(source, client)
        except BuildError as error:
            if str(error) not in errors:
                errors.append(str(error))
            continue
        prefix = f"ds.{source.alias}."
        params.append((prefix + "datasourceName", f"{client.name} {TYPE_LABELS[source.type]}"))
        params.extend((prefix + key, value) for key, value in connection)
        replacements.append({"alias": source.alias, "type": source.type, "target": target})

    if errors:
        raise BuildError(f"客戶「{client.key}」的 ID 格式有誤：{'；'.join(errors)}")

    return {
        "url": f"{BASE_URL}?{urlencode(params, quote_via=quote)}",
        "report_name": name,
        "replacements": replacements,
    }
