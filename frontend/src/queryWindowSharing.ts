import { broadcastQueryClient } from "@tanstack/query-broadcast-client-experimental";
import { type QueryClient } from "@tanstack/react-query";

const QUERY_BROADCAST_CHANNEL = "halpha-query-cache-v1";

export function configureQueryWindowSharing(queryClient: QueryClient): () => void {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return () => undefined;
  }

  try {
    return broadcastQueryClient({
      queryClient,
      broadcastChannel: QUERY_BROADCAST_CHANNEL,
    });
  } catch {
    // Cache sharing is an optimization. A browser channel failure must not
    // prevent the trading workbench from loading or reading server facts.
    return () => undefined;
  }
}
