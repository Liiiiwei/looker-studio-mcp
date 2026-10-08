import json

import pytest

from editor_script import StepError, build_script


def test_script_is_a_single_page_function_with_steps_embedded():
    steps = [{"op": "select", "x": 335, "y": 325}, {"op": "set_select", "label": "行高", "option": "32px"}]
    script = build_script(steps, screenshot=".playwright-mcp/done.png")

    assert script.lstrip().startswith("async (page) => {")
    assert script.rstrip().endswith("}")
    assert json.dumps(steps, ensure_ascii=False) in script
    assert '".playwright-mcp/done.png"' in script
    assert "const OPS = {" in script


def test_unknown_op_is_rejected_with_valid_ops_listed():
    with pytest.raises(StepError) as error:
        build_script([{"op": "explode"}])
    assert "第 1 步" in str(error.value)
    assert "explode" in str(error.value)
    assert "set_select" in str(error.value)


def test_missing_field_names_the_step_and_field():
    with pytest.raises(StepError) as error:
        build_script([{"op": "select", "x": 1}, {"op": "rename_field", "from": "Impressions"}])
    message = str(error.value)
    assert "第 1 步" in message and "y" in message
    assert "第 2 步" in message and "to" in message


def test_empty_steps_are_rejected():
    with pytest.raises(StepError, match="至少要有一個步驟"):
        build_script([])


def test_text_with_quotes_and_backticks_stays_inside_json():
    steps = [{"op": "type_text", "x": 1, "y": 2, "text": '`${page}` "引號"'}]
    script = build_script(steps)
    assert json.dumps(steps, ensure_ascii=False) in script
