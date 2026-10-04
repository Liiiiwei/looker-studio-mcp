"""讀取並驗證範本清單與客戶清單。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

SOURCE_TYPES = ("meta_windsor", "google_ads", "ga4", "sheets")


class RegistryError(Exception):
    """設定檔缺漏或格式錯誤。"""


@dataclass(frozen=True)
class Source:
    """範本裡的一個資料來源：別名、類型，sheets 類型另帶試算表名稱。"""

    alias: str
    type: str
    sheet: str | None = None


@dataclass(frozen=True)
class Template:
    key: str
    name: str
    report_id: str
    sources: tuple[Source, ...]


def _load_yaml(path: str | Path, top_key: str, hint: str = "") -> dict:
    """讀 YAML 並取出最上層的 top_key；缺檔、格式錯誤、內容為空都報錯。"""
    path = Path(path)
    if not path.exists():
        raise RegistryError(f"找不到設定檔：{path}{hint}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise RegistryError(f"{path.name} 不是合法的 YAML：{error}") from error
    section = data.get(top_key) if isinstance(data, dict) else None
    if not isinstance(section, dict) or not section:
        raise RegistryError(f"{path.name} 最上層必須有非空的「{top_key}」")
    return section


def _text(value) -> str | None:
    """把 YAML 讀到的值轉成去空白的字串；None 與空字串回傳 None，數字 0 是有效值。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_templates(path: str | Path) -> dict[str, Template]:
    templates: dict[str, Template] = {}
    for key, body in _load_yaml(path, "templates").items():
        key = str(key)
        if not isinstance(body, dict):
            raise RegistryError(f"範本「{key}」的內容必須是對照表")
        report_id = _text(body.get("report_id"))
        if not report_id:
            raise RegistryError(f"範本「{key}」缺少 report_id")
        raw_sources = body.get("sources")
        if not isinstance(raw_sources, dict) or not raw_sources:
            raise RegistryError(f"範本「{key}」的 sources 不可為空")

        sources = []
        for alias, raw in raw_sources.items():
            alias = str(alias)
            source_type = _text(raw.get("type")) if isinstance(raw, dict) else None
            if source_type not in SOURCE_TYPES:
                raise RegistryError(
                    f"範本「{key}」的別名「{alias}」type 必須是 {'、'.join(SOURCE_TYPES)} 其中之一"
                )
            sheet = _text(raw.get("sheet")) if source_type == "sheets" else None
            if source_type == "sheets" and not sheet:
                raise RegistryError(f"範本「{key}」的別名「{alias}」是 sheets 類型，必須指定 sheet")
            sources.append(Source(alias, source_type, sheet))

        templates[key] = Template(
            key=key,
            name=_text(body.get("name")) or key,
            report_id=report_id,
            sources=tuple(sources),
        )
    return templates


@dataclass(frozen=True)
class SheetRef:
    spreadsheet_id: str | None
    worksheet_id: str | None


@dataclass(frozen=True)
class Client:
    key: str
    name: str
    meta_account_id: str | None
    google_ads_account_id: str | None
    ga4_account_id: str | None
    ga4_property_id: str | None
    sheets: dict[str, SheetRef]


def _mapping(value, where: str) -> dict:
    """選填區塊：沒填回傳空對照表，填了但不是對照表就報錯。"""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RegistryError(f"{where} 必須是對照表")
    return value


def load_clients(path: str | Path) -> dict[str, Client]:
    hint = "；請複製 clients.example.yaml 為 clients.yaml 再填入帳戶 ID"
    clients: dict[str, Client] = {}
    for key, body in _load_yaml(path, "clients", hint).items():
        key = str(key)
        if not isinstance(body, dict):
            raise RegistryError(f"客戶「{key}」的內容必須是對照表")
        ga4 = _mapping(body.get("ga4"), f"客戶「{key}」的 ga4")
        raw_sheets = _mapping(body.get("sheets"), f"客戶「{key}」的 sheets")

        sheets = {}
        for sheet_name, raw in raw_sheets.items():
            ref = _mapping(raw, f"客戶「{key}」的 sheets.{sheet_name}")
            sheets[str(sheet_name)] = SheetRef(
                spreadsheet_id=_text(ref.get("spreadsheet_id")),
                worksheet_id=_text(ref.get("worksheet_id")),
            )

        clients[key] = Client(
            key=key,
            name=_text(body.get("name")) or key,
            meta_account_id=_text(body.get("meta_account_id")),
            google_ads_account_id=_text(body.get("google_ads_account_id")),
            ga4_account_id=_text(ga4.get("account_id")),
            ga4_property_id=_text(ga4.get("property_id")),
            sheets=sheets,
        )
    return clients


def missing_fields(client: Client, template: Template) -> list[str]:
    """列出客戶為了套用這份範本還缺的欄位路徑，依範本來源順序、不重複。"""
    missing: list[str] = []

    def need(value, label: str) -> None:
        if not value and label not in missing:
            missing.append(label)

    for source in template.sources:
        if source.type == "meta_windsor":
            need(client.meta_account_id, "meta_account_id")
        elif source.type == "google_ads":
            need(client.google_ads_account_id, "google_ads_account_id")
        elif source.type == "ga4":
            need(client.ga4_account_id, "ga4.account_id")
            need(client.ga4_property_id, "ga4.property_id")
        else:
            ref = client.sheets.get(source.sheet)
            need(ref.spreadsheet_id if ref else None, f"sheets.{source.sheet}.spreadsheet_id")
            need(ref.worksheet_id if ref else None, f"sheets.{source.sheet}.worksheet_id")
    return missing
