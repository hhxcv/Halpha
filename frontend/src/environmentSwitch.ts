export type VenueAccountType =
  | "USDM_DEMO"
  | "USDM_COPY_LEAD"
  | "USDM_PERSONAL";

export type TradingContextTarget = {
  venue_account_type: VenueAccountType;
  environment_id: string;
  account_id: string;
  url: string;
};

const LOOPBACK_HOSTS: ReadonlySet<string> = new Set([
  "127.0.0.1",
  "localhost",
]);

export function tradingContextLabel(accountType: string): string {
  if (accountType === "USDM_DEMO") return "Demo";
  if (accountType === "USDM_COPY_LEAD") return "实盘 · 带单账户";
  if (accountType === "USDM_PERSONAL") return "实盘 · 个人账户";
  return "交易上下文未知";
}

export function tradingAccountLabel(accountType: string): string {
  if (accountType === "USDM_DEMO") return "Demo 合约账户";
  if (accountType === "USDM_COPY_LEAD") return "带单员公域合约账户";
  if (accountType === "USDM_PERSONAL") return "个人 USDⓈ-M 合约账户";
  return "账户类型未知";
}

/**
 * Resolve one configured context to a safe, context-neutral entry route.
 *
 * Context switching is a complete document navigation between isolated App
 * instances. Object ids, query parameters and fragments must never cross that
 * boundary. A same-origin target is the current context and is not navigable.
 */
export function tradingContextSwitchTarget(
  target: TradingContextTarget | null | undefined,
  currentPageUrl: string,
): string | null {
  if (!target?.url.trim()) return null;
  try {
    const current = new URL(currentPageUrl);
    const destination = new URL(target.url);
    if (
      destination.protocol !== "http:"
      || !LOOPBACK_HOSTS.has(destination.hostname)
      || destination.username
      || destination.password
      || destination.origin === current.origin
    ) {
      return null;
    }
    destination.pathname = "/overview";
    destination.search = "";
    destination.hash = "";
    return destination.toString();
  } catch {
    return null;
  }
}
