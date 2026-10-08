"""把一串編輯步驟組成一支 Playwright 腳本，一次跑完、最後只截一張圖。

用法：uv run python editor_script.py steps.json -o run.js --screenshot .playwright-mcp/done.png
產出的 run.js 交給 Playwright MCP 的 browser_run_code_unsafe（filename 參數）執行。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HELPERS_PATH = Path(__file__).with_name("editor_helpers.js")

# 每種步驟必填的欄位；實作在 editor_helpers.js 的 OPS
STEP_FIELDS = {
    "goto": ("url",),
    "select": ("x", "y"),
    "tab": ("name",),
    "set_select": ("label", "option"),
    "pick_color": ("label", "col", "row"),
    "rename_field": ("from", "to"),
    "set_field": ("from", "to"),
    "compare_previous": (),
    "copy_paste": (),
    "drag": ("from", "to"),
    "type_text": ("x", "y", "text"),
    "click": ("x", "y"),
    "press": ("key",),
    "mode": ("name",),
    "wait": ("ms",),
}


class StepError(Exception):
    """步驟清單有誤，無法組出腳本。"""


def _check(steps: list[dict]) -> None:
    if not steps:
        raise StepError("至少要有一個步驟")
    errors: list[str] = []
    for number, step in enumerate(steps, start=1):
        op = step.get("op")
        if op not in STEP_FIELDS:
            errors.append(f"第 {number} 步的 op「{op}」不存在，可用：{'、'.join(STEP_FIELDS)}")
            continue
        missing = [field for field in STEP_FIELDS[op] if field not in step]
        if missing:
            errors.append(f"第 {number} 步（{op}）缺少：{'、'.join(missing)}")
    if errors:
        raise StepError("；".join(errors))


def build_script(steps: list[dict], screenshot: str | None = None) -> str:
    _check(steps)
    helpers = HELPERS_PATH.read_text(encoding="utf-8")
    return (
        "async (page) => {\n"
        f"{helpers}\n"
        f"const STEPS = {json.dumps(steps, ensure_ascii=False)};\n"
        f"return await run(STEPS, {json.dumps(screenshot, ensure_ascii=False)});\n"
        "}\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="把編輯步驟組成 Playwright 腳本")
    parser.add_argument("steps", type=Path, help="步驟清單（JSON 陣列）")
    parser.add_argument("-o", "--output", type=Path, required=True, help="輸出的腳本路徑")
    parser.add_argument("--screenshot", help="跑完後的截圖路徑")
    args = parser.parse_args()

    steps = json.loads(args.steps.read_text(encoding="utf-8"))
    try:
        script = build_script(steps, args.screenshot)
    except StepError as error:
        raise SystemExit(str(error))
    args.output.write_text(script, encoding="utf-8")
    print(f"{len(steps)} 個步驟 → {args.output}")


if __name__ == "__main__":
    main()
