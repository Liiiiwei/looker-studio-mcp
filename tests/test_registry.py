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


def test_duplicate_client_key_is_rejected(tmp_path):
    text = (
        "clients:\n"
        "  happyhabit:\n"
        "    meta_account_id: '111'\n"
        "  happyhabit:\n"
        "    meta_account_id: '222'\n"
    )
    with pytest.raises(RegistryError, match="重複的鍵「happyhabit」"):
        load_clients(write(tmp_path, "clients.yaml", text))


def test_duplicate_template_alias_is_rejected(tmp_path):
    text = (
        "templates:\n"
        "  a:\n"
        "    report_id: x\n"
        "    sources:\n"
        "      ds0: { type: ga4 }\n"
        "      ds0: { type: google_ads }\n"
    )
    with pytest.raises(RegistryError, match="重複的鍵「ds0」"):
        load_templates(write(tmp_path, "templates.yaml", text))
