import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";

async function assertAccessible(page: Page, testInfo: TestInfo, name: string) {
  const result = await new AxeBuilder({ page }).analyze();
  const violations = result.violations.map(({ id, impact, nodes }) => ({
    id,
    impact,
    nodeCount: nodes.length,
    nodes: nodes.map((node) => ({
      target: node.target,
      html: node.html,
      failureSummary: node.failureSummary,
    })),
  }));
  await testInfo.attach(`${name}-axe.json`, {
    body: Buffer.from(JSON.stringify({ url: page.url(), violations }, null, 2)),
    contentType: "application/json",
  });
  expect(violations).toEqual([]);
}

type TestViewport = {
  name: string;
  width: number;
  height: number;
};

type LayoutRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

const directExecutionViewports = {
  desktop: [
    { name: "desktop-1440x1000", width: 1440, height: 1000 },
    { name: "desktop-1123x920", width: 1123, height: 920 },
    { name: "desktop-1024x768", width: 1024, height: 768 },
    { name: "desktop-768x900", width: 768, height: 900 },
  ],
  narrow: [
    { name: "narrow-390x844", width: 390, height: 844 },
  ],
} satisfies Record<string, TestViewport[]>;

function rectsIntersect(left: LayoutRect, right: LayoutRect, tolerance = 0.5) {
  return left.x < right.x + right.width - tolerance
    && left.x + left.width > right.x + tolerance
    && left.y < right.y + right.height - tolerance
    && left.y + left.height > right.y + tolerance;
}

async function expectNoOverlap(
  left: Locator,
  right: Locator,
  message: string,
) {
  await expect(left).toBeVisible();
  await expect(right).toBeVisible();
  const [leftBox, rightBox] = await Promise.all([left.boundingBox(), right.boundingBox()]);
  expect(leftBox, `${message}：左侧元素缺少布局框`).not.toBeNull();
  expect(rightBox, `${message}：右侧元素缺少布局框`).not.toBeNull();
  expect(
    rectsIntersect(leftBox!, rightBox!),
    `${message}：${JSON.stringify({ left: leftBox, right: rightBox })}`,
  ).toBe(false);
}

async function assertEditorSectionHeadingClear(
  page: Page,
  headingName: string,
  firstFieldLabel: string,
) {
  const heading = page.getByRole("heading", { name: headingName, exact: true });
  const section = heading.locator("xpath=ancestor::section[1]");
  const field = section.getByLabel(firstFieldLabel, { exact: true });
  const formControl = field.locator(
    "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' MuiFormControl-root ')][1]",
  );
  const fieldLabel = formControl.locator(".MuiInputLabel-root").first();
  const fieldOutline = formControl.locator("fieldset").first();
  await heading.scrollIntoViewIfNeeded();
  await expectNoOverlap(heading, fieldLabel, `${headingName}标题不得覆盖首个字段标签`);
  await expectNoOverlap(heading, fieldOutline, `${headingName}标题不得覆盖首个字段边框`);
}

async function assertChartHeaderClear(chartRegion: Locator) {
  const subtitle = chartRegion.getByText(/输入线可拖动/).first();
  const toolButtons = chartRegion.getByRole("button", {
    name: /^(拖动选择区间|支撑 \/ 阻力|趋势线|清除分析线)$/,
  });
  await subtitle.scrollIntoViewIfNeeded();
  await expect(toolButtons).toHaveCount(4);
  for (let index = 0; index < await toolButtons.count(); index += 1) {
    const toolButton = toolButtons.nth(index);
    await expectNoOverlap(
      subtitle,
      toolButton,
      `图表副标题不得覆盖工具栏第 ${index + 1} 个按钮`,
    );
  }
}

async function assertLastChartDetailReachable(
  chartRegion: Locator,
  testInfo: TestInfo,
  viewportName: string,
) {
  const detailItems = chartRegion.locator([
    '[aria-label="图中价格标注及等价数值"] > li',
    '[aria-label="图中相对和动态价格规则"] > li',
    '[aria-label="图中分析绘图及锚点"] > li',
  ].join(", "));
  await expect(detailItems.first()).toBeAttached();
  const lastDetail = detailItems.last();
  const scrollTarget = await lastDetail.evaluate((element) => {
    const scrollingElement = document.scrollingElement as HTMLElement | null;
    let current = element.parentElement;
    while (current && current !== document.body && current !== document.documentElement) {
      const style = window.getComputedStyle(current);
      if (
        /^(auto|scroll|overlay)$/.test(style.overflowY)
        && current.scrollHeight > current.clientHeight + 1
      ) {
        return {
          kind: "element",
          tag: current.tagName,
          testId: current.dataset.testid ?? null,
          overflowY: style.overflowY,
        };
      }
      current = current.parentElement;
    }
    return {
      kind: "document",
      tag: scrollingElement?.tagName ?? null,
      testId: null,
      overflowY: scrollingElement ? window.getComputedStyle(scrollingElement).overflowY : null,
    };
  });

  await lastDetail.scrollIntoViewIfNeeded();
  const visibility = await lastDetail.evaluate((element) => {
    const elementRect = element.getBoundingClientRect();
    const clippingAncestors: Array<{
      tag: string;
      testId: string | null;
      overflowY: string;
      top: number;
      bottom: number;
    }> = [];
    let visibleTop = 0;
    let visibleBottom = window.innerHeight;
    let current = element.parentElement;
    while (current && current !== document.documentElement) {
      const style = window.getComputedStyle(current);
      if (/^(auto|scroll|overlay|hidden|clip)$/.test(style.overflowY)) {
        const bounds = current.getBoundingClientRect();
        visibleTop = Math.max(visibleTop, bounds.top);
        visibleBottom = Math.min(visibleBottom, bounds.bottom);
        clippingAncestors.push({
          tag: current.tagName,
          testId: current.dataset.testid ?? null,
          overflowY: style.overflowY,
          top: bounds.top,
          bottom: bounds.bottom,
        });
      }
      current = current.parentElement;
    }
    return {
      element: {
        top: elementRect.top,
        bottom: elementRect.bottom,
        height: elementRect.height,
      },
      visibleTop,
      visibleBottom,
      clippingAncestors,
      fullyVisible: elementRect.height > 0
        && elementRect.top >= visibleTop - 1
        && elementRect.bottom <= visibleBottom + 1,
    };
  });
  await testInfo.attach(`${viewportName}-chart-detail-scroll.json`, {
    body: Buffer.from(JSON.stringify({ scrollTarget, visibility }, null, 2)),
    contentType: "application/json",
  });
  expect(
    scrollTarget.kind === "document"
      || /^(auto|scroll|overlay)$/.test(scrollTarget.overflowY ?? ""),
    `图表详情必须由文档或显式纵向滚动容器承载：${JSON.stringify(scrollTarget)}`,
  ).toBe(true);
  expect(
    visibility.fullyVisible,
    `展开详情的最后一条等价值/分析项被 overflow 永久裁剪：${JSON.stringify(visibility)}`,
  ).toBe(true);
}

async function assertNoDocumentHorizontalOverflow(
  page: Page,
  testInfo: TestInfo,
  viewportName: string,
) {
  const layout = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    offenders: [...document.querySelectorAll<HTMLElement>("body *")]
      .filter((element) => !element.classList.contains("MuiSwitch-input"))
      .filter((element) => {
        const drawer = element.closest<HTMLElement>(".MuiDrawer-paper");
        if (!drawer) return true;
        const bounds = drawer.getBoundingClientRect();
        return bounds.right > 0 && bounds.left < document.documentElement.clientWidth;
      })
      .map((element) => {
        const bounds = element.getBoundingClientRect();
        return {
          tag: element.tagName,
          testId: element.dataset.testid ?? null,
          left: bounds.left,
          right: bounds.right,
          text: element.textContent?.trim().slice(0, 100) ?? "",
        };
      })
      .filter(({ left, right }) => left < -0.5 || right > document.documentElement.clientWidth + 0.5),
  }));
  await testInfo.attach(`${viewportName}-horizontal-overflow.json`, {
    body: Buffer.from(JSON.stringify(layout, null, 2)),
    contentType: "application/json",
  });
  expect(
    layout.scrollWidth,
    `文档出现横向溢出：${JSON.stringify(layout.offenders.slice(0, 10))}`,
  ).toBe(layout.clientWidth);
}

test("direct execution layout stays usable without overlap or clipped chart details", async ({ page }, testInfo) => {
  const attemptedTradingWrites: string[] = [];
  await page.route(/\/api\/v1\/plans(?:\/[^/?#]+\/activate)?(?:\?.*)?$/, async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      attemptedTradingWrites.push(request.url());
      await route.abort();
      return;
    }
    await route.continue();
  });
  await page.route(/\/api\/v1\/activations(?:\/.*)?(?:\?.*)?$/, async (route) => {
    const request = route.request();
    if (request.method() !== "GET" && request.method() !== "HEAD") {
      attemptedTradingWrites.push(request.url());
      await route.abort();
      return;
    }
    await route.continue();
  });

  const viewports = testInfo.project.name === "chromium-narrow"
    ? directExecutionViewports.narrow
    : directExecutionViewports.desktop;
  await page.setViewportSize(viewports[0]!);
  await page.goto("/plans/new");
  await page.getByRole("button", { name: "配置订单计划", exact: true }).click();
  const chartRegion = page.locator('section[aria-labelledby="order-schedule-chart-title"]');
  await expect(chartRegion).toBeVisible();
  await chartRegion.getByText(/图线、动态规则与等价数值/).click();

  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await page.evaluate(() => new Promise<void>((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
    }));

    await assertChartHeaderClear(chartRegion);
    await assertEditorSectionHeadingClear(page, "下单金额", "下单额模式");
    await assertEditorSectionHeadingClear(page, "初始止损", "初始止损距离（bps）");
    await assertLastChartDetailReachable(chartRegion, testInfo, viewport.name);
    await assertNoDocumentHorizontalOverflow(page, testInfo, viewport.name);
  }

  expect(attemptedTradingWrites, "布局回归只允许读取行情和生成安全预览").toEqual([]);
  await expect(page).toHaveURL(/\/plans\/new$/);
});

test("direct execution uses one live stream while chart timeframes switch", async ({ page }, testInfo) => {
  test.setTimeout(45_000);
  const websocketUrls: string[] = [];
  const marketWindowIntervals: string[] = [];
  const marketWindowPurposes: string[] = [];
  const attemptedTradingWrites: string[] = [];
  let quoteFrames = 0;
  let barFrames = 0;
  let previewRequests = 0;

  page.on("websocket", (socket) => {
    if (!socket.url().includes("/api/v1/market-stream")) return;
    websocketUrls.push(socket.url());
    socket.on("framereceived", ({ payload }) => {
      const text = typeof payload === "string" ? payload : payload.toString("utf8");
      try {
        const event = JSON.parse(text) as { type?: string };
        if (event.type === "quote") quoteFrames += 1;
        if (event.type === "bar") barFrames += 1;
      } catch {
        // The product parser owns malformed-frame handling; this counter is evidence only.
      }
    });
  });
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/api/v1/market-window") {
      marketWindowIntervals.push(url.searchParams.get("interval") ?? "");
      marketWindowPurposes.push(url.searchParams.get("purpose") ?? "");
    }
    if (url.pathname === "/api/v1/order-schedules/preview") {
      previewRequests += 1;
    }
  });
  await page.route(/\/api\/v1\/plans(?:\/.*)?(?:\?.*)?$/, async (route) => {
    const request = route.request();
    if (request.method() !== "GET" && request.method() !== "HEAD") {
      attemptedTradingWrites.push(request.url());
      await route.abort();
      return;
    }
    await route.continue();
  });
  await page.route(/\/api\/v1\/activations(?:\/.*)?(?:\?.*)?$/, async (route) => {
    const request = route.request();
    if (request.method() !== "GET" && request.method() !== "HEAD") {
      attemptedTradingWrites.push(request.url());
      await route.abort();
      return;
    }
    await route.continue();
  });

  await page.goto("/plans/new");
  await page.getByRole("button", { name: "配置订单计划", exact: true }).click();
  const chartRegion = page.locator('section[aria-labelledby="order-schedule-chart-title"]');
  await expect(chartRegion).toBeVisible();
  await expect(page.getByText("实时", { exact: true }).first()).toBeVisible({
    timeout: 15_000,
  });
  await expect.poll(() => quoteFrames, { timeout: 15_000 }).toBeGreaterThanOrEqual(2);
  await expect.poll(() => barFrames, { timeout: 15_000 }).toBeGreaterThanOrEqual(1);
  await expect(chartRegion.getByRole("status")).toHaveCount(0, { timeout: 15_000 });
  await expect(chartRegion.getByTestId("order-schedule-chart-market-source"))
    .toHaveText("Demo · Binance K线");

  const selectInterval = async (interval: "1m" | "1h") => {
    if (testInfo.project.name === "chromium-narrow") {
      await chartRegion.getByLabel("K 线周期").click();
      await page.getByRole("option", { name: interval, exact: true }).click();
    } else {
      await chartRegion
        .getByRole("group", { name: "K 线周期" })
        .getByRole("button", { name: interval, exact: true })
        .click();
    }
    await expect(chartRegion.getByRole("heading", {
      name: `${interval} K 线 · 草稿投影`,
      exact: true,
    })).toBeVisible();
    await expect.poll(
      () => marketWindowIntervals.filter((value) => value === interval).length,
      { timeout: 15_000 },
    ).toBeGreaterThanOrEqual(1);
    await expect(chartRegion.getByRole("status")).toHaveCount(0, { timeout: 15_000 });
  };

  await selectInterval("1h");
  await selectInterval("1m");
  await expect(page.getByRole("button", { name: "保存并检查" })).toBeEnabled({
    timeout: 15_000,
  });
  const previewBaseline = previewRequests;
  await page.waitForTimeout(1_500);
  expect(
    previewRequests,
    "实时行情 tick 不得持续触发订单计划预览",
  ).toBe(previewBaseline);
  expect(websocketUrls).toHaveLength(1);
  expect(new Set(marketWindowPurposes)).toEqual(new Set(["EXECUTION_REVIEW"]));
  expect(attemptedTradingWrites).toEqual([]);
});

test("runtime environment change hard-reloads and discards the old planning workspace", async ({ page }, testInfo) => {
  test.skip(
    testInfo.project.name === "chromium-narrow",
    "The environment boundary is viewport-independent and is covered once on desktop.",
  );
  test.setTimeout(30_000);
  let statusRequests = 0;
  await page.clock.install();
  await page.route("**/api/v1/settings/status", async (route) => {
    const response = await route.fetch();
    const status = await response.json() as Record<string, unknown>;
    statusRequests += 1;
    const switched = statusRequests > 1;
    await route.fulfill({
      response,
      contentType: "application/json",
      body: JSON.stringify({
        ...status,
        environment_kind: switched ? "LIVE" : "DEMO",
        environment_id: switched ? "e2e-live-primary" : "e2e-demo-primary",
      }),
    });
  });

  await page.goto("/plans/new");
  await page.getByRole("button", { name: "配置订单计划", exact: true }).click();
  await expect(page.getByTestId("direct-execution-workspace")).toBeVisible();

  await page.clock.fastForward(30_500);
  await expect.poll(() => statusRequests, { timeout: 15_000 }).toBeGreaterThanOrEqual(3);
  await expect(page.getByTestId("direct-execution-workspace")).toHaveCount(0);
  await expect(page.getByText("LIVE", { exact: true }).first()).toBeVisible();
  await expect(page).toHaveURL(/\/plans\/new$/);
});

test("Demo chart rejects Live history and Live stream frames before a clean reload", async ({ page }, testInfo) => {
  test.skip(
    testInfo.project.name === "chromium-narrow",
    "Market-source isolation is viewport-independent and is covered once on desktop.",
  );
  let routedSocket: {
    send: (message: string | Buffer) => void;
  } | null = null;
  const marketWindowPurposes: string[] = [];
  let serveWrongSource = true;

  await page.route("**/api/v1/market-window?**", async (route) => {
    const url = new URL(route.request().url());
    marketWindowPurposes.push(url.searchParams.get("purpose") ?? "");
    const interval = url.searchParams.get("interval") ?? "15m";
    const intervalMs = interval === "1m"
      ? 60_000
      : interval === "5m"
        ? 5 * 60_000
        : interval === "15m"
          ? 15 * 60_000
          : interval === "1h"
            ? 60 * 60_000
            : interval === "4h"
              ? 4 * 60 * 60_000
              : 24 * 60 * 60_000;
    const requestedStart = Date.parse(url.searchParams.get("start_at") ?? "");
    const startAt = Number.isFinite(requestedStart)
      ? requestedStart
      : Date.parse("2026-07-22T00:00:00Z");
    const bars = Array.from({ length: 12 }, (_value, index) => {
      const openAt = startAt + index * intervalMs;
      const open = 65_000 + index * 4;
      const close = open + (index % 2 === 0 ? 2 : -2);
      return {
        open_at: new Date(openAt).toISOString(),
        close_at: new Date(openAt + intervalMs).toISOString(),
        open: String(open),
        high: String(Math.max(open, close) + 3),
        low: String(Math.min(open, close) - 3),
        close: String(close),
        volume: String(10 + index),
      };
    });
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        instrument_ref: "BTCUSDT-PERP",
        interval,
        source: serveWrongSource ? "BINANCE_LIVE_PUBLIC" : "BINANCE_DEMO_PUBLIC",
        source_cutoff: url.searchParams.get("end_at") ?? "2026-07-23T10:00:00Z",
        bars,
      }),
    });
  });

  const streamBar = (source: string) => JSON.stringify({
    type: "bar",
    instrument_ref: "BTCUSDT-PERP",
    interval: "15m",
    source,
    source_cutoff: "2026-07-23T10:01:00.000Z",
    received_at: new Date().toISOString(),
    closed: false,
    bar: {
      open_at: "2026-07-23T10:00:00.000Z",
      close_at: "2026-07-23T10:15:00.000Z",
      open: "65050",
      high: "65060",
      low: "65045",
      close: "65055",
      volume: "20",
    },
  });
  await page.routeWebSocket(/\/api\/v1\/market-stream/, (socket) => {
    routedSocket = socket;
    const observedAt = new Date().toISOString();
    socket.send(JSON.stringify({
      type: "status",
      state: "LIVE",
      source: "BINANCE_DEMO_PUBLIC",
      observed_at: observedAt,
      reason: null,
    }));
    socket.send(JSON.stringify({
      type: "quote",
      instrument_ref: "BTCUSDT-PERP",
      source: "BINANCE_DEMO_PUBLIC",
      source_cutoff: observedAt,
      received_at: observedAt,
      bid_price: "65049",
      ask_price: "65051",
      reference_price: "65050",
    }));
    socket.send(streamBar("BINANCE_LIVE_PUBLIC"));
  });

  await page.goto("/plans/new");
  await page.getByRole("button", { name: "配置订单计划", exact: true }).click();
  const chartRegion = page.locator('section[aria-labelledby="order-schedule-chart-title"]');
  const chart = chartRegion.getByTestId("order-schedule-kline-chart");
  await expect(chartRegion.getByRole("status")).toContainText(
    "K 线来源与当前环境不一致",
  );
  expect(new Set(marketWindowPurposes)).toEqual(new Set(["EXECUTION_REVIEW"]));
  await expect(chart).not.toHaveAttribute("data-market-history-source");
  await expect(chart).not.toHaveAttribute("data-market-live-source");
  await expect(chartRegion.getByText("K线待同步", { exact: true })).toBeVisible();

  expect(routedSocket).not.toBeNull();
  serveWrongSource = false;
  routedSocket!.send(streamBar("BINANCE_DEMO_PUBLIC"));
  await chartRegion
    .getByRole("button", { name: "重试 K 线" })
    .evaluate((button: HTMLButtonElement) => button.click())
    .catch(() => undefined);
  await expect(chart).toHaveAttribute(
    "data-market-history-source",
    "BINANCE_DEMO_PUBLIC",
  );
  await expect(chart).toHaveAttribute(
    "data-market-live-source",
    "BINANCE_DEMO_PUBLIC",
  );
  await expect(chartRegion.getByText("Demo · Binance K线", { exact: true })).toBeVisible();
  await expect(chartRegion.getByText("K线实时", { exact: true })).toBeVisible();
});

test("Demo K-line history and a fresh Demo quote survive the other route failing", async ({ page }, testInfo) => {
  test.skip(
    testInfo.project.name === "chromium-narrow",
    "Market-route independence is viewport-independent and is covered once on desktop.",
  );
  let marketWindowRequests = 0;
  const marketWindowPurposes: string[] = [];

  await page.route("**/api/v1/market-context?**", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: { code: "DEMO_EXECUTION_MARKET_UNAVAILABLE" } }),
    });
  });
  await page.route("**/api/v1/market-window?**", async (route) => {
    marketWindowRequests += 1;
    const url = new URL(route.request().url());
    marketWindowPurposes.push(url.searchParams.get("purpose") ?? "");
    const interval = url.searchParams.get("interval") ?? "15m";
    const intervalMs = interval === "1m"
      ? 60_000
      : interval === "5m"
        ? 5 * 60_000
        : interval === "15m"
          ? 15 * 60_000
          : interval === "1h"
            ? 60 * 60_000
            : interval === "4h"
              ? 4 * 60 * 60_000
              : 24 * 60 * 60_000;
    const requestedStart = Date.parse(url.searchParams.get("start_at") ?? "");
    const startAt = Number.isFinite(requestedStart)
      ? requestedStart
      : Date.parse("2026-07-22T00:00:00Z");
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        instrument_ref: "BTCUSDT-PERP",
        interval,
        source: "BINANCE_DEMO_PUBLIC",
        source_cutoff: url.searchParams.get("end_at") ?? new Date().toISOString(),
        bars: Array.from({ length: 12 }, (_value, index) => {
          const openAt = startAt + index * intervalMs;
          return {
            open_at: new Date(openAt).toISOString(),
            close_at: new Date(openAt + intervalMs).toISOString(),
            open: String(65_000 + index),
            high: String(65_006 + index),
            low: String(64_996 + index),
            close: String(65_002 + index),
            volume: String(10 + index),
          };
        }),
      }),
    });
  });
  await page.routeWebSocket(/\/api\/v1\/market-stream/, (socket) => {
    const observedAt = new Date().toISOString();
    socket.send(JSON.stringify({
      type: "quote",
      instrument_ref: "BTCUSDT-PERP",
      source: "BINANCE_DEMO_PUBLIC",
      source_cutoff: observedAt,
      received_at: observedAt,
      bid_price: "12345",
      ask_price: "12346",
      reference_price: "12345.5",
    }));
    socket.send(JSON.stringify({
      type: "status",
      state: "RECONNECTING",
      source: "BINANCE_DEMO_PUBLIC",
      observed_at: observedAt,
      reason: "MARKET_STREAM_RECONNECTED",
    }));
  });

  await page.goto("/plans/new");
  await page.getByRole("button", { name: "配置订单计划", exact: true }).click();
  const chartRegion = page.locator('section[aria-labelledby="order-schedule-chart-title"]');
  const chart = chartRegion.getByTestId("order-schedule-kline-chart");

  await expect.poll(() => marketWindowRequests).toBeGreaterThanOrEqual(1);
  expect(new Set(marketWindowPurposes)).toEqual(new Set(["EXECUTION_REVIEW"]));
  await expect(chart).toHaveAttribute(
    "data-market-history-source",
    "BINANCE_DEMO_PUBLIC",
  );
  await expect(page.getByText("重连中", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("12,345.50", { exact: true }).first()).toBeVisible();
  await expect(chartRegion.getByText("Demo · Binance K线", { exact: true })).toBeVisible();
});

test("direct execution reconnects the local market stream and resynchronizes history", async ({ page }, testInfo) => {
  test.skip(
    testInfo.project.name === "chromium-narrow",
    "Transport recovery is viewport-independent and is covered once on desktop.",
  );
  test.setTimeout(30_000);
  const routedSockets: Array<{
    close: (options?: { code?: number; reason?: string }) => Promise<void>;
    send: (message: string | Buffer) => void;
  }> = [];
  let marketWindowRequests = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/v1/market-window") {
      marketWindowRequests += 1;
    }
  });
  await page.routeWebSocket(/\/api\/v1\/market-stream/, (socket) => {
    routedSockets.push(socket);
    const connectionNumber = routedSockets.length;
    const observedAt = new Date().toISOString();
    const reference = connectionNumber === 1 ? "100.5" : "101.5";
    socket.send(JSON.stringify({
      type: "status",
      state: "LIVE",
      source: "BINANCE_DEMO_PUBLIC",
      observed_at: observedAt,
      reason: null,
    }));
    socket.send(JSON.stringify({
      type: "quote",
      instrument_ref: "BTCUSDT-PERP",
      source: "BINANCE_DEMO_PUBLIC",
      source_cutoff: observedAt,
      received_at: observedAt,
      bid_price: connectionNumber === 1 ? "100" : "101",
      ask_price: connectionNumber === 1 ? "101" : "102",
      reference_price: reference,
    }));
    socket.send(JSON.stringify({
      type: "bar",
      instrument_ref: "BTCUSDT-PERP",
      interval: "15m",
      source: "BINANCE_DEMO_PUBLIC",
      source_cutoff: observedAt,
      received_at: observedAt,
      closed: false,
      bar: {
        open_at: "2026-07-23T11:30:00.000Z",
        close_at: "2026-07-23T11:45:00.000Z",
        open: "100",
        high: "102",
        low: "99",
        close: reference,
        volume: "10",
      },
    }));
  });

  await page.goto("/plans/new");
  await page.getByRole("button", { name: "配置订单计划", exact: true }).click();
  await expect(page.getByText("实时", { exact: true }).first()).toBeVisible({
    timeout: 10_000,
  });
  await expect(page.getByText("100.50", { exact: true }).first()).toBeVisible();
  await expect.poll(() => routedSockets.length).toBe(1);
  await expect.poll(() => marketWindowRequests, { timeout: 10_000 })
    .toBeGreaterThanOrEqual(1);
  const initialMarketWindowRequests = marketWindowRequests;

  await routedSockets[0]!.close({ code: 1012, reason: "QUALIFICATION_RECONNECT" });
  await expect(page.getByText("重连中", { exact: true }).first()).toBeVisible();
  await expect.poll(() => routedSockets.length, { timeout: 10_000 }).toBe(2);
  await expect(page.getByText("实时", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("101.50", { exact: true }).first()).toBeVisible();
  await expect.poll(() => marketWindowRequests, { timeout: 10_000 })
    .toBeGreaterThan(initialMarketWindowRequests);
});

test("direct execution keeps the K-line chart as the primary annotated workspace", async ({ page }, testInfo) => {
  const attemptedPlanCreates: string[] = [];
  await page.route(/\/api\/v1\/plans(?:\?.*)?$/, async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      attemptedPlanCreates.push(request.url());
      await route.abort();
      return;
    }
    await route.continue();
  });
  if (testInfo.project.name === "chromium-desktop") {
    await page.setViewportSize({ width: 1123, height: 920 });
  }
  await page.goto("/plans/new");
  await page.getByRole("button", { name: "配置订单计划", exact: true }).click();
  await expect(page.getByRole("heading", { name: "直接执行" })).toBeVisible();
  await expect(page.getByRole("button", { name: /重新选择/ })).toHaveCount(0);
  await expect(page.getByText("已选执行依据", { exact: true })).toHaveCount(0);

  const saveButton = page.getByRole("button", { name: "保存并检查" });

  const chartRegion = page.getByRole("region", { name: "15m K 线 · 草稿投影" });
  const chart = chartRegion.getByRole("group", {
    name: /订单计划 15m K 线主图/,
  });
  const chartDetail = chartRegion.getByText(/图线、动态规则与等价数值/);
  await chartDetail.click();
  const priceAnnotations = chartRegion.getByRole("list", {
    name: "图中价格标注及等价数值",
  });
  await expect(chartRegion).toBeVisible();
  await expect(chart).toBeVisible();
  await expect(page.getByLabel("限价（USDT）")).not.toHaveValue("");
  await expect(priceAnnotations).toContainText("当前计量参考价");
  await expect(priceAnnotations).toContainText("输入限价");
  await expect(chartRegion.getByRole("list", {
    name: "图中相对和动态价格规则",
  })).toContainText("每笔成交后止损 · 100 bps");

  const rangeButton = chartRegion.getByRole("button", { name: "拖动选择区间" });
  await expect(rangeButton).toBeDisabled();
  if (testInfo.project.name === "chromium-desktop") {
    await expect(chartRegion.getByRole("button", { name: "支撑 / 阻力" })).toBeEnabled();
    await expect(chartRegion.getByRole("button", { name: "趋势线" })).toBeEnabled();
  } else {
    await expect(chartRegion.getByRole("button", { name: "支撑 / 阻力" })).toBeDisabled();
    await expect(chartRegion.getByRole("button", { name: "趋势线" })).toBeDisabled();
  }

  await page.getByRole("button", { name: "区间阶梯" }).click();
  await page.getByLabel("下限（USDT）", { exact: true }).fill("65000");
  await page.getByLabel("上限（USDT）", { exact: true }).fill("66000");
  await page.getByLabel("每档金额（USDT）").fill("100");
  await expect(priceAnnotations).toContainText("区间下限");
  await expect(priceAnnotations).toContainText("区间上限");
  await expect(chartRegion).toContainText("标准化入场 1/5", { timeout: 15_000 });

  await page.getByText("条件与触发", { exact: true }).click();
  await page.getByRole("checkbox", { name: "标记价格条件" }).check();
  await expect(priceAnnotations).toContainText("标记价条件 ≥");
  await page.getByRole("checkbox", { name: "买卖价差上限" }).check();
  await expect(chartRegion.getByRole("list", {
    name: "图中相对和动态价格规则",
  })).toContainText("价差 ≤ 10 bps");

  if (testInfo.project.name === "chromium-desktop") {
    await expect(rangeButton).toBeEnabled();
    await rangeButton.click();
    const dragLayer = chartRegion.getByTestId("order-schedule-range-drag-layer");
    await expect(dragLayer).toBeVisible();
    await chart.press("Escape");
    await expect(dragLayer).toHaveCount(0);

    const beforeRange = await Promise.all([
      page.getByLabel("下限（USDT）", { exact: true }).inputValue(),
      page.getByLabel("上限（USDT）", { exact: true }).inputValue(),
    ]);
    await rangeButton.click();
    const bounds = await dragLayer.boundingBox();
    expect(bounds).not.toBeNull();
    await page.mouse.move(bounds!.x + bounds!.width * .45, bounds!.y + bounds!.height * .25);
    await page.mouse.down();
    await page.mouse.move(
      bounds!.x + bounds!.width * .45,
      bounds!.y + bounds!.height * .72,
      { steps: 6 },
    );
    await page.mouse.up();
    await expect(dragLayer).toHaveCount(0);
    await expect.poll(async () => Promise.all([
      page.getByLabel("下限（USDT）", { exact: true }).inputValue(),
      page.getByLabel("上限（USDT）", { exact: true }).inputValue(),
    ])).not.toEqual(beforeRange);
    await chart.press("Escape");
    await expect(page.getByLabel("下限（USDT）", { exact: true })).toHaveValue(beforeRange[0]!);
    await expect(page.getByLabel("上限（USDT）", { exact: true })).toHaveValue(beforeRange[1]!);
  } else {
    await expect(rangeButton).toBeDisabled();
  }

  await assertAccessible(page, testInfo, `direct-order-chart-${testInfo.project.name}`);
  await testInfo.attach(`direct-order-chart-${testInfo.project.name}.png`, {
    body: await chartRegion.screenshot(),
    contentType: "image/png",
  });

  const layout = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    viewportHeight: window.innerHeight,
    pageHeight: document.documentElement.scrollHeight,
    configClientHeight: document.querySelector<HTMLElement>("[data-testid='direct-order-config-scroll']")?.clientHeight ?? 0,
    configScrollHeight: document.querySelector<HTMLElement>("[data-testid='direct-order-config-scroll']")?.scrollHeight ?? 0,
  }));
  expect(layout.scrollWidth).toBe(layout.clientWidth);
  if (testInfo.project.name === "chromium-desktop") {
    expect(layout.pageHeight).toBe(layout.viewportHeight);
    expect(layout.configScrollHeight).toBeGreaterThan(layout.configClientHeight);
    await expect(saveButton).toBeVisible();
    await expect(page.getByRole("switch", { name: "Maker only" })).toBeVisible();
    await expect(page.getByLabel("初始止损距离（bps）")).toBeVisible();
  }

  const capitalLimit = page.getByLabel("资金上限（USDT）");
  await capitalLimit.fill("0");
  await expect(saveButton).toBeDisabled();
  await capitalLimit.press("Enter");
  await page.waitForTimeout(300);
  expect(attemptedPlanCreates).toEqual([]);
  await expect(page).toHaveURL(/\/plans\/new$/);
});

test("direct execution chart keeps its fixed empty state when K-line history fails", async ({ page }) => {
  await page.route("**/api/v1/market-window?**", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: { code: "MARKET_WINDOW_TEST_FAILURE" } }),
    });
  });
  await page.routeWebSocket(/\/api\/v1\/market-stream/, (socket) => {
    const observedAt = new Date().toISOString();
    socket.send(JSON.stringify({
      type: "status",
      state: "LIVE",
      source: "BINANCE_DEMO_PUBLIC",
      observed_at: observedAt,
      reason: null,
    }));
    socket.send(JSON.stringify({
      type: "quote",
      instrument_ref: "BTCUSDT-PERP",
      source: "BINANCE_DEMO_PUBLIC",
      source_cutoff: observedAt,
      received_at: observedAt,
      bid_price: "65000",
      ask_price: "65002",
      reference_price: "65001",
    }));
  });
  await page.goto("/plans/new");
  await page.getByRole("button", { name: "配置订单计划", exact: true }).click();

  const chartRegion = page.getByRole("region", { name: "15m K 线 · 草稿投影" });
  await expect(chartRegion.getByRole("group", {
    name: /订单计划 15m K 线主图/,
  })).toBeVisible();
  await expect(chartRegion.getByRole("status")).toContainText("K 线窗口读取失败");
  await expect(chartRegion.getByRole("button", { name: "重试 K 线" })).toBeVisible();
  await expect(chartRegion.getByTestId("order-schedule-chart-market-source")).toHaveCount(0);
  await chartRegion.getByText(/图线、动态规则与等价数值/).click();
  await expect(chartRegion.getByText("图中价格线与等价数值")).toBeVisible();
});

test("planning and limited-control surfaces preserve authority and failure boundaries", async ({ page }, testInfo) => {
  const planName = `E2E AI Donchian ${Date.now()}`;
  await page.goto("/overview");
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByText("DEMO", { exact: true })).toBeVisible();
  await expect(page.getByText("真实账户交易", { exact: false })).toHaveCount(0);
  await expect(page.getByText("刷新于", { exact: false })).toBeVisible();
  await assertAccessible(page, testInfo, "overview");

  const navigation = page.getByRole("navigation", { name: "工作台导航" });
  if (testInfo.project.name === "chromium-desktop") {
    await expect(page.getByRole("button", { name: "折叠导航" })).toBeVisible();
    await page.getByRole("button", { name: "折叠导航" }).click();
    await expect(page.getByRole("button", { name: "展开导航" })).toBeVisible();
    await expect(navigation.getByRole("button", { name: "总览" })).toBeVisible();
    await expect(navigation.getByText("总览", { exact: true })).toHaveCount(0);
    await assertAccessible(page, testInfo, "overview-navigation-collapsed");
    await page.reload();
    await expect(page.getByRole("button", { name: "展开导航" })).toBeVisible();
    await page.getByRole("button", { name: "展开导航" }).click();
    await expect(page.getByRole("button", { name: "折叠导航" })).toBeVisible();
  } else {
    await expect(page.getByRole("button", { name: "打开导航" })).toBeVisible();
    await page.getByRole("button", { name: "打开导航" }).click();
    await expect(navigation.getByText("总览", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: /折叠导航|展开导航/ })).toHaveCount(0);
    await navigation.getByRole("button", { name: "总览" }).click();
  }

  await page.goto("/plans/new");
  await expect(page.getByRole("heading", { name: "选择执行依据" })).toBeVisible();
  await expect(page.getByText("DEMO", { exact: true })).toBeVisible();
  await expect(page.getByLabel("筛选策略")).toBeVisible();
  await expect(page.getByLabel("支持方向")).toBeVisible();
  await expect(page.getByRole("combobox", { name: "排序" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "配置策略计划" })).toHaveCount(0);
  await page.getByLabel("筛选策略").fill("Donchian");
  await expect(page.getByText("单次 Donchian 突破与 ATR 风险退出", { exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "排序" }).click();
  await page.getByRole("option", { name: "策略版本（新到旧）" }).click();
  await page.getByRole("button", { name: /展开.*策略介绍/ }).click();
  await expect(page.getByText("价值逻辑", { exact: true })).toBeVisible();
  await assertAccessible(page, testInfo, "strategy-selection");
  await page.getByRole("button", { name: "配置策略" }).click();
  await expect(page.getByRole("heading", { name: "配置策略计划" })).toBeVisible();
  await expect(page.getByRole("button", { name: "保存计划" })).toBeVisible();
  await expect(page.getByRole("button", { name: "重新选择策略" })).toBeVisible();
  await page.getByLabel("计划名称").fill(planName);
  await page.getByRole("combobox", { name: "创建方式" }).click();
  await page.getByRole("option", { name: "AI 创建" }).click();
  await expect(page.getByLabel("交易对象")).toHaveValue("BTCUSDT-PERP");
  await expect(page.getByLabel("交易金额（USDT）")).toHaveValue("500");
  await expect(page.getByText("高级策略参数（可保持默认）")).toBeVisible();
  await assertAccessible(page, testInfo, "new-plan");
  await testInfo.attach("new-plan.png", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
  await page.getByRole("button", { name: "保存计划" }).click();
  await expect(page).toHaveURL(/\/plans$/);
  await expect(page.getByRole("heading", { name: "交易计划" })).toBeVisible();
  await expect(page.getByRole("tab", { name: /当前计划/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /历史计划/ })).toBeVisible();
  await expect(page.getByText("了解当前可用策略", { exact: false })).toHaveCount(0);
  const planCard = page.getByRole("article", { name: `计划 ${planName}` });
  await expect(planCard.getByRole("heading", { name: planName })).toBeVisible();
  await expect(planCard.getByText(/AI 创建 · 创建于 .* UTC\+8/)).toBeVisible();
  await expect(planCard.getByText("BTCUSDT-PERP", { exact: false })).toBeVisible();
  await planCard.getByText("计划配置", { exact: true }).click();
  await expect(planCard.getByText("交易金额", { exact: true })).toBeVisible();
  await expect(planCard.getByText("500.00 USDT", { exact: true })).toBeVisible();
  await expect(planCard.getByText("15m 通道回看", { exact: true })).toBeVisible();
  await expect(planCard.getByText("初始止损", { exact: true })).toBeVisible();
  await expect(page.getByText("价值逻辑", { exact: true })).toHaveCount(0);
  await planCard.getByRole("button", { name: "删除草稿" }).click();
  const deleteDialog = page.getByRole("dialog", { name: "删除草稿？" });
  await expect(deleteDialog.getByText(planName, { exact: false })).toBeVisible();
  await deleteDialog.getByRole("button", { name: "取消" }).click();
  await expect(planCard).toBeVisible();
  await planCard.getByRole("button", { name: "删除草稿" }).click();
  await deleteDialog.getByRole("button", { name: "删除草稿" }).click();
  await expect(planCard).toHaveCount(0);

  await page.goto("/operations");
  await expect(page.getByRole("heading", { name: "故障接管" })).toBeVisible();
  await expect(page.getByText("DEMO", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "打开 Binance 官方入口" })).toBeVisible();
  const activation = page.locator("article.activation").filter({ hasText: "WRITER_CONTINUITY_LOST" }).first();
  if (await activation.count() === 0) {
    test.info().annotations.push({
      type: "coverage-gap",
      description: "当前运行库没有 WRITER_CONTINUITY_LOST 激活；保留计划流程结果，跳过依赖该状态的故障接管演练。",
    });
    return;
  }
  await expect(activation).toBeVisible();
  const activationId = await activation.getAttribute("data-activation-id");
  expect(activationId).toBeTruthy();
  await expect(activation.getByText(/PAUSED · WRITER_CONTINUITY_LOST/)).toBeVisible();
  await expect(activation.getByText("恢复激活", { exact: false })).toHaveCount(0);
  await assertAccessible(page, testInfo, "operations-before");

  const stopControl = activation.locator(".control").filter({ hasText: "停止新增风险" });
  await stopControl.getByRole("button", { name: "查看后果" }).click();
  const dialog = page.getByRole("dialog", { name: "确认故障控制" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("停止新增风险", { exact: true })).toBeVisible();
  await expect(dialog.getByText("只停止新的开仓和加仓", { exact: false })).toBeVisible();
  await assertAccessible(page, testInfo, "stop-preview");
  await dialog.getByRole("button", { name: "取消" }).click();

  const exitControl = activation.locator(".control").filter({ hasText: "退出策略" });
  await exitControl.getByRole("button", { name: "查看后果" }).click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "确认退出策略" }).click();
  await expect(activation.getByRole("status")).toContainText("EFFECTIVE · 回执");
  await expect(activation.getByRole("status")).toContainText("EXIT_WITHOUT_VENUE_RESPONSIBILITY_COMPLETED");
  await page.reload();
  await expect(page.locator(`article.activation[data-activation-id="${activationId}"]`)).toHaveCount(0);
  await assertAccessible(page, testInfo, "operations-after-exit");
  await testInfo.attach("operations-after-exit.png", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });

  const layout = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    offenders: [...document.querySelectorAll<HTMLElement>("body *")]
      .filter((element) => !element.closest(".table-scroll"))
      .map((element) => {
        const bounds = element.getBoundingClientRect();
        return {
          tag: element.tagName,
          className: element.className,
          left: bounds.left,
          right: bounds.right,
          text: element.textContent?.trim().slice(0, 120) ?? "",
        };
      })
      .filter(({ left, right }) => left < -0.5 || right > document.documentElement.clientWidth + 0.5),
  }));
  await testInfo.attach("operations-layout.json", {
    body: Buffer.from(JSON.stringify(layout, null, 2)),
    contentType: "application/json",
  });
  expect(layout.offenders).toEqual([]);
  expect(layout.scrollWidth).toBe(layout.clientWidth);
});
