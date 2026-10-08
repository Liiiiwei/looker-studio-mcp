// Looker Studio 編輯器的操作手法（2026-10-05 在 1680×1000 視窗實測）。
// 這段會被 editor_script.py 包進 `async (page) => { ... }`，交給 Playwright 執行。
// 屬性面板在畫面右側 x 1120–1360；座標類參數都是視窗座標。

const PANEL = {
  left: 1125,
  right: 1340,
  iconX: 1145,
  chipX: 1250,
  toggleX: 1312,
};
const pause = (ms) => page.waitForTimeout(ms);

// 屬性面板裡，文字完全相符的元素的位置
const panelBoxes = (text) =>
  page.locator(`text="${text}"`).evaluateAll(
    (els, p) =>
      els
        .map((e) => e.getBoundingClientRect())
        .filter((r) => r.x > p.left && r.x < p.right && r.width > 0)
        .map((r) => ({ x: r.x, y: r.y, w: r.width, h: r.height })),
    PANEL,
  );

const panelBox = async (text) => {
  const boxes = await panelBoxes(text);
  if (!boxes.length) throw new Error(`屬性面板找不到「${text}」`);
  return boxes[0];
};

const tab = async (name) => {
  await page.locator(`text="${name}"`).first().click();
  await pause(700);
};

// 樣式面板的欄位標籤（下拉選單、色盤都靠它定位）
const fieldLabel = async (label) => {
  const l = page
    .locator(`mat-label:text-is("${label}"), label:text-is("${label}")`)
    .first();
  if (!(await l.count())) throw new Error(`樣式面板找不到欄位「${label}」`);
  await l.scrollIntoViewIfNeeded();
  await pause(300);
  return l.boundingBox();
};

const OPS = {
  async select({ x, y }) {
    await page.mouse.click(x, y);
    await pause(1300);
  },

  async tab({ name }) {
    await tab(name);
  },

  // 樣式面板的下拉選單：依標籤找欄位，依文字選值
  async set_select({ label, option }) {
    await tab("樣式");
    const bb = await fieldLabel(label);
    await page.mouse.click(bb.x + 40, bb.y + 22);
    await pause(800);
    const all = page.locator('[role="option"]');
    const texts = (await all.allInnerTexts()).map((s) => s.trim());
    const index = texts.indexOf(option);
    if (index < 0) {
      await page.keyboard.press("Escape");
      throw new Error(
        `「${label}」沒有選項「${option}」，可用：${texts.join("、")}`,
      );
    }
    await all.nth(index).click();
    await pause(1200);
  },

  // 色盤：第一列是灰階（第 10 格是白），第二列起是彩色；col、row 從 1 起算
  async pick_color({ label, col, row }) {
    await tab("樣式");
    const bb = await fieldLabel(label);
    await page.mouse.click(bb.x + 60, bb.y + 22);
    await pause(900);
    const overlay = page.locator(".cdk-overlay-container");
    const reset = overlay.locator('text="重設"');
    const clear = overlay.locator('text="透明"');
    let anchor;
    let firstRow;
    if (await reset.count()) {
      anchor = await reset.last().boundingBox();
      firstRow = 35;
    } else if (await clear.count()) {
      anchor = await clear.last().boundingBox();
      firstRow = 37;
    } else {
      await page.keyboard.press("Escape");
      throw new Error(
        `「${label}」的色盤沒有「重設」或「透明」可當定位點，改用 click 步驟配合截圖`,
      );
    }
    const cx = anchor.x + anchor.width / 2;
    const cy = anchor.y + anchor.height / 2;
    await page.mouse.click(
      cx - 31 + 26 * (col - 1),
      cy + firstRow + 26 * (row - 1),
    );
    await pause(1200);
  },

  // 只改這張圖表上的顯示名稱，不動資料來源
  async rename_field({ from, to }) {
    await tab("設定");
    const chip = await panelBox(from);
    await page.mouse.click(PANEL.iconX, chip.y + chip.h / 2);
    await pause(1200);
    const name = page.locator('text="顯示名稱"').last();
    if (!(await name.count())) {
      await page.keyboard.press("Escape");
      throw new Error(`「${from}」的欄位設定視窗沒有開啟`);
    }
    await name.click();
    await page.keyboard.press("Meta+a");
    await page.keyboard.type(to);
    await pause(400);
    await page.mouse.click(1240, 300);
    await pause(1500);
  },

  // 把圖表上的欄位換成資料來源的另一個欄位
  async set_field({ from, to }) {
    await tab("設定");
    const chip = await panelBox(from);
    await page.mouse.click(PANEL.chipX, chip.y + chip.h / 2);
    await pause(1000);
    const search = page.locator('input[placeholder="搜尋"]').first();
    await search.fill(to);
    await pause(1200);
    const bb = await search.boundingBox();
    let hit = null;
    for (let dy = 30; dy < 260 && !hit; dy += 6) {
      const row = await page.evaluate(
        ({ x, y }) => {
          const e = document.elementFromPoint(x, y);
          if (!e) return null;
          const b = e.getBoundingClientRect();
          return { text: (e.innerText || "").trim(), top: b.top, h: b.height };
        },
        { x: 1220, y: bb.y + dy },
      );
      if (row && row.text === to && row.h < 60) hit = row;
    }
    if (!hit) {
      await page.keyboard.press("Escape");
      throw new Error(`資料來源找不到欄位「${to}」`);
    }
    // 要點在列的上下中點，點邊緣不會被接受
    await page.mouse.click(1220, hit.top + hit.h / 2);
    await pause(3000);
  },

  // 開啟「比較日期範圍」並選上一個時段
  async compare_previous() {
    await tab("設定");
    const label = page.locator('text="比較日期範圍"').first();
    await label.scrollIntoViewIfNeeded();
    await pause(300);
    let bb = await label.boundingBox();
    await page.mouse.click(PANEL.toggleX, bb.y + bb.height / 2);
    await pause(1500);
    bb = await label.boundingBox();
    await page.mouse.click(1232, bb.y + bb.height / 2 + 34);
    await pause(1200);
    const none = await page.locator('text="無"').last().boundingBox();
    await page.mouse.click(none.x + 60, none.y + none.height / 2);
    await pause(900);
    const previous = page.locator('text="上一個時段"').last();
    if (!(await previous.count())) {
      await page.keyboard.press("Escape");
      await page.keyboard.press("Escape");
      throw new Error("比較類型裡找不到「上一個時段」");
    }
    await previous.click();
    await pause(600);
    await page.locator('text="套用"').last().click();
    await pause(2500);
  },

  // 複製目前選取的元件，貼在同一個區段（樣式會一致）
  async copy_paste() {
    await page.keyboard.press("Meta+c");
    await pause(600);
    await page.keyboard.press("Meta+v");
    await pause(3500);
  },

  async drag({ from, to }) {
    await page.mouse.move(from[0], from[1]);
    await page.mouse.down();
    await page.mouse.move((from[0] + to[0]) / 2, (from[1] + to[1]) / 2, {
      steps: 6,
    });
    await page.mouse.move(to[0], to[1], { steps: 8 });
    await page.mouse.up();
    await pause(1500);
  },

  // 文字方塊：連點兩下進入編輯，整段換掉
  async type_text({ x, y, text }) {
    await page.mouse.dblclick(x, y);
    await pause(800);
    await page.keyboard.press("Meta+a");
    await page.keyboard.type(text);
    await pause(400);
    await page.mouse.click(700, 950);
    await pause(800);
  },

  async click({ x, y }) {
    await page.mouse.click(x, y);
    await pause(900);
  },

  async press({ key }) {
    await page.keyboard.press(key);
    await pause(600);
  },

  // 切換編輯／檢視模式；name 是右上角按鈕的文字（「查看」或「編輯」）
  async mode({ name }) {
    await page.locator(`button:has-text("${name}")`).first().click();
    await pause(6000);
  },

  // 開啟報表網址；Windsor 資料載入慢，預設等 12 秒
  async goto({ url }) {
    await page.goto(url);
    await pause(12000);
  },

  async wait({ ms }) {
    await pause(ms);
  },
};

const run = async (steps, screenshot) => {
  // 分頁在背景時截圖會卡到逾時
  await page.bringToFront();
  await pause(800);
  const log = [];
  for (let i = 0; i < steps.length; i += 1) {
    const { op, ...args } = steps[i];
    try {
      await OPS[op](args);
      log.push({ step: i + 1, op, ok: true });
    } catch (error) {
      log.push({
        step: i + 1,
        op,
        ok: false,
        error: String(error.message || error).split("\n")[0],
      });
      break;
    }
  }
  if (screenshot) {
    await page.mouse.click(700, 950);
    await pause(1000);
    await page.screenshot({ path: screenshot, timeout: 20000 });
  }
  return {
    url: page.url(),
    done: log.filter((entry) => entry.ok).length,
    total: steps.length,
    log,
  };
};
