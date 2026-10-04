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
