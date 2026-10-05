# Looker Studio 報表 MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 做一個本機 MCP server，依「客戶 × 範本」組出 Looker Studio Linking API 網址，打開即是已換好該客戶資料來源的報表預覽。

**Architecture:** 三個模組各管一件事：`registry.py` 把兩份 YAML 讀成驗證過的資料物件；`url_builder.py` 是不碰檔案與網路的純函式，把客戶與範本變成網址；`server.py` 用 FastMCP 把兩者接成三個工具。設定檔每次呼叫重新讀取，改完 YAML 不必重啟。

**Tech Stack:** Python 3.11 以上、官方 MCP Python SDK（`mcp.server.fastmcp.FastMCP`）、PyYAML、pytest、uv。

**Spec:** `docs/superpowers/specs/2026-10-05-looker-studio-mcp-design.md`

## Global Constraints

- 專案根目錄：`/Users/vincentsia/Desktop/vibe-coding playground/looker-studio-mcp/`，以下路徑皆相對於此
- 所有指令在專案根目錄執行，Python 一律透過 `uv run`
- 程式碼註解、docstring、錯誤訊息、工具說明一律繁體中文
- 來源類型只有四種：`meta_windsor`、`google_ads`、`ga4`、`sheets`
- Linking API 基底網址：`https://lookerstudio.google.com/reporting/create`
- Windsor 連接器 ID：`AKfycbwMs3jUvu_RtMs6XtlspAdiMR8X19N1DAi8mYOCfUxy6I3NHhXRR9qkqxg83fG2js71`
- 各類型的連線參數（鍵名大小寫不可改）：
  - `meta_windsor`：`connector=community`、`connectorId=<Windsor 連接器 ID>`、`configuredAccountsSelector=facebook__<帳戶 ID>`
  - `google_ads`：`connector=googleAds`、`accountId=<10 碼數字>`
  - `ga4`：`connector=googleAnalytics`、`accountId`、`propertyId`
  - `sheets`：`connector=googleSheets`、`spreadsheetId`、`worksheetId`
- 範本列出的每個別名都必須替換；客戶缺任何一項就報錯，不產出網址
- `clients.yaml` 不進版控
- 不得刪檔用 `rm -rf`；要刪用 `trash`
- Commit 訊息用 Conventional Commits；分支名 `vs/{description}`
- 實地驗收只開預覽，不按「編輯及共用」，不修改任何既有報表

## Review Focus

1. YAML 裡 ID 沒加引號被讀成數字，或 `worksheet_id: 0` 被當成「沒填」→ 應視為有效字串 `"0"`（Task 2 測試 `test_unquoted_ids_and_zero_worksheet`）
2. Google Ads ID 帶連字號（`123-456-7890`）、Meta ID 帶 `act_` 前綴 → 應自動正規化後照常產出網址（Task 3 測試 `test_ids_are_normalized`）
3. 第一次使用時還沒有 `clients.yaml` → 錯誤訊息要指出檔案路徑並提示從 `clients.example.yaml` 複製（Task 2 測試 `test_missing_clients_file_hints_example`）
4. 報表名稱含空白、`&`、中文 → 不可截斷或拆成額外參數（Task 3 測試 `test_report_name_is_encoded`）
5. 範本要的試算表名稱在客戶資料裡不存在（客戶有 `sheets`，但沒有那一份）→ 缺項清單要明確寫出 `sheets.<名稱>.*`（Task 2 測試 `test_missing_fields_lists_everything`）

---

### Task 1: 專案骨架與範本清單載入

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `registry.py`
- Create: `tests/test_registry.py`

**Interfaces:**
- Consumes: 無
- Produces（`registry.py`）:
  - `SOURCE_TYPES: tuple[str, ...]` = `("meta_windsor", "google_ads", "ga4", "sheets")`
  - `class RegistryError(Exception)`
  - `@dataclass(frozen=True) class Source`：`alias: str`、`type: str`、`sheet: str | None = None`
  - `@dataclass(frozen=True) class Template`：`key: str`、`name: str`、`report_id: str`、`sources: tuple[Source, ...]`
  - `load_templates(path: str | Path) -> dict[str, Template]`
  - 內部輔助（Task 2 會沿用）：`_load_yaml(path, top_key: str, hint: str = "") -> dict`、`_text(value) -> str | None`

- [ ] **Step 1: 先把規格與計畫提交到 main，再開實作分支**

目前儲存庫在尚未有任何提交的 `vs/design-spec` 分支上。

```bash
git branch -m main
git add docs/
git commit -m "docs: add design spec and implementation plan"
git checkout -b vs/mcp-server
```

- [ ] **Step 2: 建立 `pyproject.toml`**

```toml
[project]
name = "looker-studio-mcp"
version = "0.1.0"
description = "依客戶與範本組出 Looker Studio Linking API 網址的 MCP server"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.2.0",
    "pyyaml>=6.0",
]

[dependency-groups]
dev = ["pytest>=8.0"]

[tool.uv]
package = false

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 3: 建立 `.gitignore`**

```gitignore
# 客戶帳戶 ID，不進版控
clients.yaml

.venv/
__pycache__/
.pytest_cache/
```

- [ ] **Step 4: 安裝相依套件**

Run: `uv sync`
Expected: 建立 `.venv/` 與 `uv.lock`，結尾列出已安裝的 `mcp`、`pyyaml`、`pytest`，無錯誤。

- [ ] **Step 5: 寫會失敗的測試 `tests/test_registry.py`**

```python
import pytest

from registry import RegistryError, Source, load_templates


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


VALID_TEMPLATES = """\
templates:
  ecommerce:
    name: 電商成效報表
    report_id: 10c6e47c-64d9-41fa-a5b2-cad7602627b0
    sources:
      ds8: { type: meta_windsor }
      ds25: { type: google_ads }
      ds0: { type: ga4 }
      ds119: { type: sheets, sheet: budget }
"""


def test_load_templates_valid(tmp_path):
    templates = load_templates(write(tmp_path, "templates.yaml", VALID_TEMPLATES))

    assert list(templates) == ["ecommerce"]
    template = templates["ecommerce"]
    assert template.key == "ecommerce"
    assert template.name == "電商成效報表"
    assert template.report_id == "10c6e47c-64d9-41fa-a5b2-cad7602627b0"
    assert template.sources == (
        Source("ds8", "meta_windsor"),
        Source("ds25", "google_ads"),
        Source("ds0", "ga4"),
        Source("ds119", "sheets", "budget"),
    )


def test_template_name_defaults_to_key(tmp_path):
    text = "templates:\n  lead:\n    report_id: abc\n    sources:\n      ds1: { type: ga4 }\n"
    templates = load_templates(write(tmp_path, "templates.yaml", text))
    assert templates["lead"].name == "lead"


def test_missing_templates_file(tmp_path):
    with pytest.raises(RegistryError, match="找不到設定檔"):
        load_templates(tmp_path / "templates.yaml")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("templates: [unclosed", "templates.yaml 不是合法的 YAML"),
        ("", "最上層必須有非空的「templates」"),
        ("templates: {}", "最上層必須有非空的「templates」"),
        ("templates:\n  a:\n    sources:\n      ds1: { type: ga4 }\n", "範本「a」缺少 report_id"),
        ("templates:\n  a:\n    report_id: x\n", "範本「a」的 sources 不可為空"),
        ("templates:\n  a:\n    report_id: x\n    sources: {}\n", "範本「a」的 sources 不可為空"),
        (
            "templates:\n  a:\n    report_id: x\n    sources:\n      ds1: { type: tiktok }\n",
            "範本「a」的別名「ds1」type 必須是",
        ),
        (
            "templates:\n  a:\n    report_id: x\n    sources:\n      ds1: ga4\n",
            "範本「a」的別名「ds1」type 必須是",
        ),
        (
            "templates:\n  a:\n    report_id: x\n    sources:\n      ds1: { type: sheets }\n",
            "範本「a」的別名「ds1」是 sheets 類型，必須指定 sheet",
        ),
    ],
)
def test_invalid_templates(tmp_path, text, expected):
    with pytest.raises(RegistryError, match=expected):
        load_templates(write(tmp_path, "templates.yaml", text))
```

- [ ] **Step 6: 執行測試確認失敗**

Run: `uv run pytest tests/test_registry.py -v`
Expected: 收集階段就失敗，訊息含 `ModuleNotFoundError: No module named 'registry'`。

- [ ] **Step 7: 實作 `registry.py`**

```python
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
```

- [ ] **Step 8: 執行測試確認通過**

Run: `uv run pytest tests/test_registry.py -v`
Expected: 12 passed。

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml uv.lock .gitignore registry.py tests/test_registry.py
git commit -m "feat: load and validate template registry"
```

---

### Task 2: 客戶清單載入與缺項檢查

**Files:**
- Modify: `registry.py`（在檔尾追加）
- Modify: `tests/test_registry.py`（在檔尾追加，並改第一段 import）

**Interfaces:**
- Consumes（Task 1）：`RegistryError`、`Template`、`Source`、`_load_yaml`、`_text`
- Produces（`registry.py`）:
  - `@dataclass(frozen=True) class SheetRef`：`spreadsheet_id: str | None`、`worksheet_id: str | None`
  - `@dataclass(frozen=True) class Client`：`key: str`、`name: str`、`meta_account_id: str | None`、`google_ads_account_id: str | None`、`ga4_account_id: str | None`、`ga4_property_id: str | None`、`sheets: dict[str, SheetRef]`
  - `load_clients(path: str | Path) -> dict[str, Client]`
  - `missing_fields(client: Client, template: Template) -> list[str]`，回傳欄位路徑，可能的值：`meta_account_id`、`google_ads_account_id`、`ga4.account_id`、`ga4.property_id`、`sheets.<名稱>.spreadsheet_id`、`sheets.<名稱>.worksheet_id`；依範本來源順序、不重複

- [ ] **Step 1: 寫會失敗的測試**

把 `tests/test_registry.py` 第一段 import 改成：

```python
import pytest

from registry import (
    Client,
    RegistryError,
    SheetRef,
    Source,
    Template,
    load_clients,
    load_templates,
    missing_fields,
)
```

在檔尾追加：

```python
VALID_CLIENTS = """\
clients:
  happyhabit:
    name: 每日衡好
    meta_account_id: "1234567890123456"
    google_ads_account_id: "123-456-7890"
    ga4:
      account_id: "111"
      property_id: "222"
    sheets:
      budget:
        spreadsheet_id: "1AbC"
        worksheet_id: "0"
  newbie:
    meta_account_id: "999"
"""

FULL_TEMPLATE = Template(
    key="ecommerce",
    name="電商成效報表",
    report_id="rid",
    sources=(
        Source("ds8", "meta_windsor"),
        Source("ds25", "google_ads"),
        Source("ds0", "ga4"),
        Source("ds119", "sheets", "budget"),
    ),
)


def test_load_clients_valid(tmp_path):
    clients = load_clients(write(tmp_path, "clients.yaml", VALID_CLIENTS))

    assert list(clients) == ["happyhabit", "newbie"]
    assert clients["happyhabit"] == Client(
        key="happyhabit",
        name="每日衡好",
        meta_account_id="1234567890123456",
        google_ads_account_id="123-456-7890",
        ga4_account_id="111",
        ga4_property_id="222",
        sheets={"budget": SheetRef("1AbC", "0")},
    )
    assert clients["newbie"] == Client(
        key="newbie",
        name="newbie",
        meta_account_id="999",
        google_ads_account_id=None,
        ga4_account_id=None,
        ga4_property_id=None,
        sheets={},
    )


def test_unquoted_ids_and_zero_worksheet(tmp_path):
    text = (
        "clients:\n"
        "  a:\n"
        "    meta_account_id: 1234567890123456\n"
        "    google_ads_account_id: 1234567890\n"
        "    ga4: { account_id: 111, property_id: 222 }\n"
        "    sheets:\n"
        "      budget: { spreadsheet_id: 1AbC, worksheet_id: 0 }\n"
    )
    client = load_clients(write(tmp_path, "clients.yaml", text))["a"]

    assert client.meta_account_id == "1234567890123456"
    assert client.google_ads_account_id == "1234567890"
    assert client.ga4_account_id == "111"
    assert client.sheets["budget"] == SheetRef("1AbC", "0")
    assert missing_fields(client, FULL_TEMPLATE) == []


def test_missing_clients_file_hints_example(tmp_path):
    with pytest.raises(RegistryError) as error:
        load_clients(tmp_path / "clients.yaml")
    assert "找不到設定檔" in str(error.value)
    assert str(tmp_path / "clients.yaml") in str(error.value)
    assert "clients.example.yaml" in str(error.value)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("clients:\n  a: hello\n", "客戶「a」的內容必須是對照表"),
        ("clients:\n  a:\n    ga4: 123\n", "客戶「a」的 ga4 必須是對照表"),
        ("clients:\n  a:\n    sheets: [1]\n", "客戶「a」的 sheets 必須是對照表"),
        ("clients:\n  a:\n    sheets:\n      budget: abc\n", "客戶「a」的 sheets.budget 必須是對照表"),
    ],
)
def test_invalid_clients(tmp_path, text, expected):
    with pytest.raises(RegistryError, match=expected):
        load_clients(write(tmp_path, "clients.yaml", text))


def test_missing_fields_none_when_complete(tmp_path):
    client = load_clients(write(tmp_path, "clients.yaml", VALID_CLIENTS))["happyhabit"]
    assert missing_fields(client, FULL_TEMPLATE) == []


def test_missing_fields_lists_everything(tmp_path):
    text = (
        "clients:\n"
        "  a:\n"
        "    ga4: { account_id: 111 }\n"
        "    sheets:\n"
        "      weekly: { spreadsheet_id: x, worksheet_id: 1 }\n"
    )
    client = load_clients(write(tmp_path, "clients.yaml", text))["a"]

    assert missing_fields(client, FULL_TEMPLATE) == [
        "meta_account_id",
        "google_ads_account_id",
        "ga4.property_id",
        "sheets.budget.spreadsheet_id",
        "sheets.budget.worksheet_id",
    ]


def test_missing_fields_not_repeated_for_same_type():
    template = Template("t", "t", "rid", (Source("ds1", "google_ads"), Source("ds2", "google_ads")))
    client = Client("a", "a", None, None, None, None, {})
    assert missing_fields(client, template) == ["google_ads_account_id"]
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `uv run pytest tests/test_registry.py -v`
Expected: 收集階段失敗，訊息含 `ImportError: cannot import name 'Client' from 'registry'`。

- [ ] **Step 3: 在 `registry.py` 檔尾追加實作**

```python
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
```

- [ ] **Step 4: 執行測試確認通過**

Run: `uv run pytest tests/test_registry.py -v`
Expected: 22 passed。

- [ ] **Step 5: Commit**

```bash
git add registry.py tests/test_registry.py
git commit -m "feat: load client registry and report missing fields"
```

---

### Task 3: 網址產生器

**Files:**
- Create: `url_builder.py`
- Create: `tests/test_url_builder.py`

**Interfaces:**
- Consumes（Task 1、2）：`Client`、`SheetRef`、`Source`、`Template`、`missing_fields(client, template) -> list[str]`
- Produces（`url_builder.py`）:
  - `BASE_URL: str`、`WINDSOR_CONNECTOR_ID: str`
  - `TYPE_LABELS: dict[str, str]` = `{"meta_windsor": "Meta 廣告", "google_ads": "Google Ads", "ga4": "GA4", "sheets": "試算表"}`
  - `class BuildError(Exception)`
  - `build_report_url(client: Client, template: Template, report_name: str | None = None, explain: bool = False) -> dict`，回傳 `{"url": str, "report_name": str, "replacements": list[dict]}`；`replacements` 每項為 `{"alias": str, "type": str, "target": str}`

- [ ] **Step 1: 寫會失敗的測試 `tests/test_url_builder.py`**

```python
from urllib.parse import parse_qsl

import pytest

from registry import Client, SheetRef, Source, Template
from url_builder import BASE_URL, WINDSOR_CONNECTOR_ID, BuildError, build_report_url

TEMPLATE = Template(
    key="ecommerce",
    name="電商成效報表",
    report_id="10c6e47c-64d9-41fa-a5b2-cad7602627b0",
    sources=(
        Source("ds8", "meta_windsor"),
        Source("ds25", "google_ads"),
        Source("ds0", "ga4"),
        Source("ds119", "sheets", "budget"),
    ),
)


def make_client(**overrides):
    fields = dict(
        key="happyhabit",
        name="每日衡好",
        meta_account_id="1234567890123456",
        google_ads_account_id="1234567890",
        ga4_account_id="111",
        ga4_property_id="222",
        sheets={"budget": SheetRef("1AbC_d-E", "0")},
    )
    fields.update(overrides)
    return Client(**fields)


def parse(url):
    base, _, query = url.partition("?")
    return base, dict(parse_qsl(query, keep_blank_values=True, strict_parsing=True))


def test_all_four_sources_replaced():
    result = build_report_url(make_client(), TEMPLATE)
    base, params = parse(result["url"])

    assert base == BASE_URL
    assert params == {
        "c.reportId": "10c6e47c-64d9-41fa-a5b2-cad7602627b0",
        "r.reportName": "每日衡好-電商成效報表",
        "ds.ds8.datasourceName": "每日衡好 Meta 廣告",
        "ds.ds8.connector": "community",
        "ds.ds8.connectorId": WINDSOR_CONNECTOR_ID,
        "ds.ds8.configuredAccountsSelector": "facebook__1234567890123456",
        "ds.ds25.datasourceName": "每日衡好 Google Ads",
        "ds.ds25.connector": "googleAds",
        "ds.ds25.accountId": "1234567890",
        "ds.ds0.datasourceName": "每日衡好 GA4",
        "ds.ds0.connector": "googleAnalytics",
        "ds.ds0.accountId": "111",
        "ds.ds0.propertyId": "222",
        "ds.ds119.datasourceName": "每日衡好 試算表",
        "ds.ds119.connector": "googleSheets",
        "ds.ds119.spreadsheetId": "1AbC_d-E",
        "ds.ds119.worksheetId": "0",
    }
    assert result["report_name"] == "每日衡好-電商成效報表"
    assert result["replacements"] == [
        {"alias": "ds8", "type": "meta_windsor", "target": "facebook__1234567890123456"},
        {"alias": "ds25", "type": "google_ads", "target": "1234567890"},
        {"alias": "ds0", "type": "ga4", "target": "111/222"},
        {"alias": "ds119", "type": "sheets", "target": "1AbC_d-E#0"},
    ]


def test_report_name_is_encoded():
    name = "A&B 十月 報表"
    result = build_report_url(make_client(), TEMPLATE, report_name=name)
    _, params = parse(result["url"])

    assert params["r.reportName"] == name
    assert result["report_name"] == name
    query = result["url"].partition("?")[2]
    assert "A%26B%20" in query
    assert "+" not in query
    assert " " not in query


def test_blank_report_name_falls_back_to_default():
    result = build_report_url(make_client(), TEMPLATE, report_name="   ")
    assert result["report_name"] == "每日衡好-電商成效報表"


def test_explain_flag():
    _, without = parse(build_report_url(make_client(), TEMPLATE)["url"])
    _, with_flag = parse(build_report_url(make_client(), TEMPLATE, explain=True)["url"])

    assert "c.explain" not in without
    assert with_flag["c.explain"] == "true"


def test_ids_are_normalized():
    client = make_client(meta_account_id="act_1234567890123456", google_ads_account_id="123-456-7890")
    _, params = parse(build_report_url(client, TEMPLATE)["url"])

    assert params["ds.ds8.configuredAccountsSelector"] == "facebook__1234567890123456"
    assert params["ds.ds25.accountId"] == "1234567890"


def test_invalid_ids_are_all_reported():
    client = make_client(
        meta_account_id="abc",
        google_ads_account_id="123456789",
        ga4_property_id="G-ABC123",
        sheets={"budget": SheetRef("1AbC", "Sheet1")},
    )
    with pytest.raises(BuildError) as error:
        build_report_url(client, TEMPLATE)

    message = str(error.value)
    assert "meta_account_id" in message
    assert "google_ads_account_id" in message and "10 碼數字" in message
    assert "ga4.property_id" in message
    assert "sheets.budget.worksheet_id" in message


def test_missing_fields_block_url():
    client = make_client(google_ads_account_id=None, sheets={})
    with pytest.raises(BuildError) as error:
        build_report_url(client, TEMPLATE)

    message = str(error.value)
    assert "客戶「happyhabit」缺少範本「ecommerce」需要的欄位" in message
    assert "google_ads_account_id" in message
    assert "sheets.budget.spreadsheet_id" in message
    assert "sheets.budget.worksheet_id" in message


def test_same_type_twice_gets_two_aliases():
    template = Template("t", "雙帳戶", "rid", (Source("ds1", "google_ads"), Source("ds2", "google_ads")))
    _, params = parse(build_report_url(make_client(), template)["url"])

    assert params["ds.ds1.accountId"] == "1234567890"
    assert params["ds.ds2.accountId"] == "1234567890"
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `uv run pytest tests/test_url_builder.py -v`
Expected: 收集階段失敗，訊息含 `ModuleNotFoundError: No module named 'url_builder'`。

- [ ] **Step 3: 實作 `url_builder.py`**

```python
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
```

- [ ] **Step 4: 執行測試確認通過**

Run: `uv run pytest -v`
Expected: 30 passed（Task 1、2 的 22 個加上本任務 8 個）。

- [ ] **Step 5: Commit**

```bash
git add url_builder.py tests/test_url_builder.py
git commit -m "feat: build Linking API url from client and template"
```

---

### Task 4: MCP server 與設定檔

**Files:**
- Create: `server.py`
- Create: `templates.yaml`
- Create: `clients.example.yaml`
- Create: `tests/test_server.py`

**Interfaces:**
- Consumes：`registry.load_templates`、`registry.load_clients`、`registry.missing_fields`、`url_builder.build_report_url`、`url_builder.BuildError`
- Produces（`server.py`）:
  - `mcp: FastMCP`，名稱 `looker-studio`
  - 三個工具函式：`list_templates() -> list[dict]`、`list_clients() -> list[dict]`、`build_report_url(client: str, template: str, report_name: str | None = None, explain: bool = False) -> dict`
  - 設定檔位置：環境變數 `LOOKER_STUDIO_MCP_CONFIG_DIR`，未設定時為 `server.py` 所在資料夾；底下固定讀 `templates.yaml` 與 `clients.yaml`
  - 以 `python server.py` 啟動時走 stdio

- [ ] **Step 1: 寫會失敗的測試 `tests/test_server.py`**

```python
import pytest

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
    with pytest.raises(ValueError) as error:
        server.build_report_url("nobody", "ecommerce")
    assert "找不到客戶「nobody」" in str(error.value)
    assert "happyhabit" in str(error.value) and "newbie" in str(error.value)


def test_unknown_template_lists_valid_keys(config_dir):
    with pytest.raises(ValueError) as error:
        server.build_report_url("happyhabit", "nope")
    assert "找不到範本「nope」" in str(error.value)
    assert "ecommerce" in str(error.value) and "ga_only" in str(error.value)


def test_incomplete_client_raises(config_dir):
    with pytest.raises(server.BuildError, match="客戶「newbie」缺少範本「ecommerce」需要的欄位"):
        server.build_report_url("newbie", "ecommerce")


def test_yaml_edits_take_effect_without_restart(config_dir):
    assert len(server.list_templates()) == 2
    (config_dir / "templates.yaml").write_text(
        "templates:\n  only:\n    report_id: r\n    sources:\n      ds0: { type: ga4 }\n",
        encoding="utf-8",
    )
    assert [item["key"] for item in server.list_templates()] == ["only"]
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `uv run pytest tests/test_server.py -v`
Expected: 收集階段失敗，訊息含 `ModuleNotFoundError: No module named 'server'`。

- [ ] **Step 3: 實作 `server.py`**

```python
"""Looker Studio 報表 MCP：依客戶與範本組出 Linking API 網址。"""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import url_builder
from registry import Client, load_clients, load_templates, missing_fields
from url_builder import BuildError

mcp = FastMCP("looker-studio")

PREREQUISITES = [
    "該客戶的 Meta 廣告帳戶必須已在 Windsor 連接",
    "開啟網址的 Google 帳號必須有該客戶 Google Ads、GA4 與試算表的存取權",
]
NEXT_STEP = "在已登入的瀏覽器開啟網址，確認預覽數據是該客戶的，再按右上角「編輯及共用」存成新報表"


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
```

- [ ] **Step 4: 執行測試確認通過**

Run: `uv run pytest -v`
Expected: 38 passed。

若 `test_list_templates` 等測試出現 `TypeError: 'FunctionTool' object is not callable` 之類訊息，代表安裝到的 SDK 版本的 `@mcp.tool()` 不回傳原函式。此時把三個 `@mcp.tool()` 裝飾器拿掉，改在 `if __name__ == "__main__":` 上方加這三行，再重跑測試：

```python
mcp.tool()(list_templates)
mcp.tool()(list_clients)
mcp.tool()(build_report_url)
```

- [ ] **Step 5: 建立 `templates.yaml`**

這是實測過的範本副本與它實際有圖表在用的四個別名。

```yaml
templates:
  ecommerce:
    name: 電商成效報表
    report_id: 10c6e47c-64d9-41fa-a5b2-cad7602627b0
    sources:
      ds8:   { type: meta_windsor }
      ds25:  { type: google_ads }
      ds0:   { type: ga4 }
      ds119: { type: sheets, sheet: budget }
```

- [ ] **Step 6: 建立 `clients.example.yaml`**

```yaml
# 複製成 clients.yaml 再填入真實帳戶 ID。所有 ID 請加引號。
clients:
  example:
    name: 範例客戶
    # Meta 廣告帳戶 ID，不含 act_ 前綴；必須已在 Windsor 連接
    meta_account_id: "1234567890123456"
    # Google Ads 客戶 ID，10 碼，有無連字號皆可
    google_ads_account_id: "123-456-7890"
    ga4:
      account_id: "123456789"
      property_id: "987654321"
    sheets:
      budget:
        # 試算表網址 /d/ 與 /edit 之間那一段
        spreadsheet_id: "1AbCdEfGhIjKlMnOpQrStUvWxYz"
        # 工作表網址 gid= 後面的數字
        worksheet_id: "0"
```

- [ ] **Step 7: 確認 server 用真實設定檔能啟動並列出工具**

```bash
cp clients.example.yaml clients.yaml
uv run python - <<'EOF'
import asyncio
import server

tools = asyncio.run(server.mcp.list_tools())
print(sorted(tool.name for tool in tools))
print(server.list_templates()[0]["key"])
print(server.build_report_url("example", "ecommerce")["url"][:80])
EOF
```

Expected 三行輸出：

```
['build_report_url', 'list_clients', 'list_templates']
ecommerce
https://lookerstudio.google.com/reporting/create?c.reportId=10c6e47c-64d9-41fa-a
```

- [ ] **Step 8: 確認 `clients.yaml` 沒被版控追蹤**

Run: `git status --short`
Expected: 清單裡有 `server.py`、`templates.yaml`、`clients.example.yaml`、`tests/test_server.py`，沒有 `clients.yaml`。

- [ ] **Step 9: Commit**

```bash
git add server.py templates.yaml clients.example.yaml tests/test_server.py
git commit -m "feat: expose registry and url builder as MCP tools"
```

---

### Task 5: 掛上 Claude Code 與實地驗收

這個任務沒有新程式碼，產出是「四題驗收全過」的證據。需要使用者配合兩件事：執行註冊指令、提供一個非原客戶的真實帳戶 ID 組合。

**Files:**
- Modify: `clients.yaml`（本機檔，不進版控）

**Interfaces:**
- Consumes：Task 4 的三個工具

- [ ] **Step 1: 請使用者填一個真實客戶到 `clients.yaml`**

要用範本原客戶（每日衡好）以外的客戶，才能看出資料來源真的被換掉。需要的五項：Meta 廣告帳戶 ID、Google Ads 客戶 ID、GA4 帳戶 ID 與資源 ID、預算試算表的 ID 與工作表 gid。把 `clients.yaml` 裡的 `example` 換成該客戶，代號用英文小寫。

- [ ] **Step 2: 請使用者註冊 MCP server**

這一步會改使用者的 Claude Code 設定，由使用者自己在提示列輸入：

```
! claude mcp add --scope user looker-studio -- uv run --directory "/Users/vincentsia/Desktop/vibe-coding playground/looker-studio-mcp" python server.py
```

Run: `claude mcp list`
Expected: 清單裡有 `looker-studio`，狀態為已連線。新開一個 Claude Code 對話後才看得到工具。

- [ ] **Step 3: 驗收第一題：四個資料來源同時替換，預覽無錯誤載入**

呼叫 `build_report_url`，`client` 用 Step 1 的代號，`template` 用 `ecommerce`，`explain` 設 `true`。用 Playwright（已登入的瀏覽器）開啟回傳的網址，等到分頁標題變成報表名稱。

通過條件：沒有出現「建立報表時發生錯誤」視窗；Overview、Meta ad、Google ads、Google analytics 四頁的圖表都有數字，沒有「資料集設定錯誤」的灰框。四頁各截一張圖留存。

- [ ] **Step 4: 驗收第二題：除錯視窗確認四個別名都被取代**

在預覽頁點「瞭解這份報表的建立方式」按鈕，讀出視窗文字。

通過條件：`ds8`、`ds25`、`ds0`、`ds119` 四段都出現「先複製範本資料來源，再取代連線設定」；每段列出的網址參數與 `build_report_url` 回傳的 `replacements` 相符。

- [ ] **Step 5: 驗收第三題：三個平台各抽一個指標對後台**

把預覽的日期區間設成上個完整月份，記下：Meta 廣告花費（Meta ad 頁）、Google Ads 費用（Google ads 頁）、GA4 工作階段數（Google analytics 頁）。再從各平台取同區間的數字比對：Meta 用 Windsor MCP 的 `get_data`、GA4 用 GA4 MCP 的 `run_report`、Google Ads 用 Playwright 開廣告後台讀取。

通過條件：三個數字各自與後台相符（金額差異在 1 元以內，工作階段數完全相同）。

- [ ] **Step 6: 驗收第四題：混合資料的圖表兩側都是新客戶的數字**

在 Google ads 頁找到「規劃預算」對「實際費用」的圖表（資料來自試算表 `ds119` 與 Google Ads `ds25` 的混合），日期區間沿用 Step 5。

通過條件：規劃預算與該客戶預算試算表同期間的數字相符；實際費用與 Step 5 記下的 Google Ads 費用相符；圖表沒有「資料集設定錯誤」。截一張圖留存。

- [ ] **Step 7: 收尾**

關掉預覽分頁，不按「編輯及共用」。向使用者回報四題的結果與截圖路徑；任何一題沒過，回報實際看到的錯誤訊息或數字差異，不宣稱完成。

四題全過後，提醒使用者兩件手工：把正式範本整理成乾淨版（刪掉沒有圖表使用的資料來源、換掉客戶商標與名稱），並把乾淨版的報表 ID 與別名更新到 `templates.yaml`。
