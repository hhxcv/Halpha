import { useEffect } from "react";
import { BroadcastChannel, createLeaderElection } from "broadcast-channel";
import { focusManager } from "@tanstack/react-query";
import { useLocation } from "react-router";

const QUERY_POLLING_CHANNEL_PREFIX = "halpha-query-poll-v1";

export function queryPollingScope(route: string): string {
  const normalizedRoute = route.replace(/\/+$/, "") || "/";
  return `${QUERY_POLLING_CHANNEL_PREFIX}:${normalizedRoute}`;
}

export function configureQueryPollingLeadership(route: string): () => void {
  let channel: BroadcastChannel;
  try {
    channel = new BroadcastChannel(queryPollingScope(route), {
      webWorkerSupport: false,
    });
  } catch {
    focusManager.setFocused(true);
    return () => undefined;
  }
  const elector = createLeaderElection(channel);
  let active = true;

  // Initial queries still load in every newly opened window. Periodic refetches
  // start only after this route scope has elected one owner; successful results
  // are then distributed by the shared TanStack Query cache channel.
  focusManager.setFocused(false);
  void elector.awaitLeadership().then(
    () => {
      if (active) focusManager.setFocused(true);
    },
    () => {
      // Cross-window coordination must never make the workbench unusable on a
      // browser without a functioning channel implementation.
      if (active) focusManager.setFocused(true);
    },
  );

  return () => {
    active = false;
    focusManager.setFocused(false);
    void channel.close();
  };
}

export function QueryPollingCoordinator() {
  const { pathname, search } = useLocation();
  const route = `${pathname}${search}`;

  useEffect(() => configureQueryPollingLeadership(route), [route]);
  return null;
}
