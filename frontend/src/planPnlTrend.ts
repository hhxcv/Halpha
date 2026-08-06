export type PlanPnlPoint = {
  at: string;
  value: number;
};

export function mergePlanPnlPoints(
  points: PlanPnlPoint[],
  maxPoints: number,
): PlanPnlPoint[] {
  const limit = Math.max(4, Math.floor(maxPoints));
  if (points.length <= limit) return points;

  const first = points[0]!;
  const last = points.at(-1)!;
  const interior = points.slice(1, -1);
  const bucketCount = Math.max(1, Math.floor((limit - 2) / 2));
  const bucketSize = interior.length / bucketCount;
  const merged: PlanPnlPoint[] = [first];

  for (let bucketIndex = 0; bucketIndex < bucketCount; bucketIndex += 1) {
    const from = Math.floor(bucketIndex * bucketSize);
    const to = Math.min(
      interior.length,
      Math.floor((bucketIndex + 1) * bucketSize),
    );
    const bucket = interior.slice(from, Math.max(from + 1, to));
    if (bucket.length === 0) continue;
    let minimumIndex = 0;
    let maximumIndex = 0;
    for (let index = 1; index < bucket.length; index += 1) {
      if (bucket[index]!.value < bucket[minimumIndex]!.value) minimumIndex = index;
      if (bucket[index]!.value > bucket[maximumIndex]!.value) maximumIndex = index;
    }
    const extrema = minimumIndex === maximumIndex
      ? [bucket[minimumIndex]!]
      : minimumIndex < maximumIndex
        ? [bucket[minimumIndex]!, bucket[maximumIndex]!]
        : [bucket[maximumIndex]!, bucket[minimumIndex]!];
    merged.push(...extrema);
  }

  merged.push(last);
  return merged.length <= limit
    ? merged
    : merged.slice(0, limit - 1).concat(last);
}

type PlanFill = {
  action_kind?: unknown;
  fee?: unknown;
  fee_currency?: unknown;
  fill_time?: unknown;
  order_side?: unknown;
  price?: unknown;
  quantity?: unknown;
};

type FundingFact = {
  kind?: unknown;
  payload?: unknown;
  source_time?: unknown;
};

type PnlBar = {
  close?: unknown;
  close_at?: unknown;
};

type TimedFill = {
  atMs: number;
  cashDelta: number;
  fee: number;
  quantityDelta: number;
};

type TimedFunding = {
  atMs: number;
  income: number;
};

function recordOf(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? value as Record<string, unknown>
    : {};
}

function fillSide(fill: PlanFill, direction: string): "BUY" | "SELL" | null {
  const explicit = String(fill.order_side ?? "").toUpperCase();
  if (explicit === "BUY" || explicit === "SELL") return explicit;
  const entry = String(fill.action_kind ?? "").toUpperCase() === "ENTRY";
  if (direction === "LONG") return entry ? "BUY" : "SELL";
  if (direction === "SHORT") return entry ? "SELL" : "BUY";
  return null;
}

function timedFills(fills: PlanFill[], direction: string): TimedFill[] {
  return fills.flatMap((fill) => {
    const atMs = Date.parse(String(fill.fill_time ?? ""));
    const price = Number(fill.price);
    const quantity = Number(fill.quantity);
    const side = fillSide(fill, direction);
    if (
      !Number.isFinite(atMs)
      || !Number.isFinite(price)
      || !Number.isFinite(quantity)
      || quantity <= 0
      || side === null
    ) return [];
    const feeCurrency = String(fill.fee_currency ?? "USDT").toUpperCase();
    const rawFee = Number(fill.fee ?? 0);
    const fee = feeCurrency === "USDT" && Number.isFinite(rawFee) ? rawFee : 0;
    const quantityDelta = side === "BUY" ? quantity : -quantity;
    return [{
      atMs,
      quantityDelta,
      cashDelta: -quantityDelta * price,
      fee,
    }];
  }).sort((left, right) => left.atMs - right.atMs);
}

function timedFunding(facts: FundingFact[]): TimedFunding[] {
  return facts.flatMap((fact) => {
    if (String(fact.kind ?? "") !== "FUNDING") return [];
    const atMs = Date.parse(String(fact.source_time ?? ""));
    const income = Number(recordOf(fact.payload).income);
    return Number.isFinite(atMs) && Number.isFinite(income)
      ? [{ atMs, income }]
      : [];
  }).sort((left, right) => left.atMs - right.atMs);
}

export function buildPlanPnlTrend({
  bars,
  direction,
  fills,
  fundingFacts,
  settledAt,
  settledNetPnl,
  sourceCutoff,
  startedAt,
}: {
  bars: PnlBar[];
  direction: string;
  fills: PlanFill[];
  fundingFacts: FundingFact[];
  settledAt?: string;
  settledNetPnl?: unknown;
  sourceCutoff: string;
  startedAt: string;
}): PlanPnlPoint[] {
  const startMs = Date.parse(startedAt);
  const cutoffMs = Date.parse(sourceCutoff);
  const orderedFills = timedFills(fills, direction);
  if (!Number.isFinite(startMs) || !Number.isFinite(cutoffMs) || orderedFills.length === 0) {
    return [];
  }
  const orderedFunding = timedFunding(fundingFacts);
  const orderedBars = bars.flatMap((bar) => {
    const closeAtMs = Date.parse(String(bar.close_at ?? ""));
    const close = Number(bar.close);
    if (!Number.isFinite(closeAtMs) || !Number.isFinite(close)) return [];
    return [{
      atMs: Math.min(closeAtMs, cutoffMs),
      close,
    }];
  }).filter((bar) => bar.atMs >= startMs && bar.atMs <= cutoffMs)
    .sort((left, right) => left.atMs - right.atMs);

  let cash = 0;
  let commission = 0;
  let funding = 0;
  let position = 0;
  let fillIndex = 0;
  let fundingIndex = 0;
  const points = new Map<number, number>([[startMs, 0]]);

  orderedBars.forEach((bar) => {
    while (fillIndex < orderedFills.length && orderedFills[fillIndex]!.atMs <= bar.atMs) {
      const fill = orderedFills[fillIndex]!;
      cash += fill.cashDelta;
      commission += fill.fee;
      position += fill.quantityDelta;
      fillIndex += 1;
    }
    while (fundingIndex < orderedFunding.length && orderedFunding[fundingIndex]!.atMs <= bar.atMs) {
      funding += orderedFunding[fundingIndex]!.income;
      fundingIndex += 1;
    }
    const markedNetPnl = cash + position * bar.close - commission + funding;
    points.set(bar.atMs, Math.abs(markedNetPnl) < 1e-10 ? 0 : markedNetPnl);
  });

  const trend = [...points.entries()]
    .sort(([left], [right]) => left - right)
    .map(([atMs, value]) => ({ at: new Date(atMs).toISOString(), value }));
  const settlementAtMs = Date.parse(settledAt ?? "");
  const settlementValue = settledNetPnl === null
    || settledNetPnl === undefined
    || String(settledNetPnl).trim() === ""
    ? Number.NaN
    : Number(settledNetPnl);
  if (
    trend.length < 2
    || !Number.isFinite(settlementAtMs)
    || !Number.isFinite(settlementValue)
  ) {
    return trend;
  }
  const finalTrendAtMs = Date.parse(trend.at(-1)!.at);
  const anchoredAtMs = Math.max(settlementAtMs, finalTrendAtMs);
  const withoutExistingEndpoint = trend.filter(
    (point) => Date.parse(point.at) < anchoredAtMs,
  );
  return withoutExistingEndpoint.concat({
    at: new Date(anchoredAtMs).toISOString(),
    value: settlementValue,
  });
}
