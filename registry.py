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
