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


def test_spreadsheet_url_instead_of_id_is_rejected():
    url = "https://docs.google.com/spreadsheets/d/1AbC/edit#gid=0"
    client = make_client(sheets={"budget": SheetRef(url, "0")})
    with pytest.raises(BuildError, match="sheets.budget.spreadsheet_id"):
        build_report_url(client, TEMPLATE)


def test_fullwidth_digits_are_rejected():
    client = make_client(google_ads_account_id="１２３４５６７８９０", ga4_property_id="２２２")
    with pytest.raises(BuildError) as error:
        build_report_url(client, TEMPLATE)
    assert "google_ads_account_id" in str(error.value)
    assert "ga4.property_id" in str(error.value)
