# Benchmarking Professional Trading UX

## Purpose

Benchmark to understand professional interaction patterns, not to make Halpha look like another brand. Recheck current first-party material for every substantial redesign because product interfaces change.

## Minimum Benchmark Set

Select at least three relevant first-party products or standards:

- venue execution and position management, such as the current Binance Futures interface;
- dense configurable workstation and activity monitoring, such as Interactive Brokers TWS/Mosaic;
- linked market context, panels, and progressive workspace disclosure, such as TradingView Supercharts;
- component feedback, progress, alerts, focus, and platform polish, using Apple Human Interface Guidelines.

Replace or supplement these when another product matches the exact task better. Do not use marketing screenshots alone when official manuals, help pages, product tours, or videos expose actual interaction states.

Useful first-party starting points, to be revalidated at task time:

- TradingView Supercharts: <https://www.tradingview.com/support/solutions/43000746464-getting-started-with-supercharts/>
- TradingView chart trading: <https://www.tradingview.com/support/solutions/43000766334-chart-trading-on-tradingview-key-features-and-advantages/>
- IBKR TWS overview: <https://www.interactivebrokers.com/campus/trading-lessons/getting-started-with-tws/>
- IBKR Activity Monitor: <https://www.interactivebrokers.com/campus/trading-lessons/tws-activity-monitor/>
- Apple alerts: <https://developer.apple.com/design/human-interface-guidelines/alerts>
- Apple progress indicators: <https://developer.apple.com/design/human-interface-guidelines/progress-indicators>

## Comparison Matrix

Record observations with screenshots or links and compare these dimensions:

| Dimension | Questions |
|---|---|
| User and task | Which expert job and time pressure does the pattern serve? |
| Scan order | What is readable immediately? Treat 1-3 seconds as a prototype heuristic unless an accepted test owns the timing target. |
| Information density | How many useful comparable facts fit without becoming ambiguous? |
| Spatial stability | Do positions, orders, risk, activity, and controls stay in predictable locations? |
| Linked context | How does instrument or object selection update adjacent panels? |
| Numeric treatment | Alignment, precision, sign, units, timestamps, and change indication |
| Action ergonomics | Click distance, keyboard support, hover actions, disabled reasons, and duplicate prevention |
| Submission feedback | Immediate acknowledgement and stable submitted identity |
| Async lifecycle | Queued, working, external wait, progress, completion, failure, and unknown visibility |
| Risk guard | Preview, confirmation, consequence, reversibility, and emergency reachability |
| Progressive disclosure | What remains visible; what moves to popovers, drawers, dialogs, tabs, or detail routes? |
| Failure recovery | Whether errors are visible, explained, actionable, and persistent enough |
| Customization | Whether expert efficiency depends on layouts; whether Halpha P0 can justify that complexity |
| Accessibility | Focus, contrast, non-color state, reduced motion, and readable density |

For each borrowed pattern, record:

1. the problem it solves;
2. why the pattern fits Halpha's accepted semantics;
3. what must not be copied;
4. the P0 complexity cost;
5. the prototype state that will validate it.

## Halpha-Specific Interpretation

Professional trading products demonstrate that compact tables, stable panels, activity monitors, direct manipulation, and continuous state feedback can reduce decision time. Halpha is not a discretionary order-entry terminal, so do not add charts, depth, hotkeys, watchlists, scanners, or instant order placement merely because benchmarks contain them.

Borrow interaction qualities:

- dense but aligned facts;
- predictable workspace regions;
- object-linked detail;
- strong order/action lifecycle visibility;
- fast access to current risk and open responsibility;
- low-noise progressive disclosure;
- explicit destructive or high-consequence confirmation.

Reject copied capabilities that conflict with P0 non-goals or create another source of truth.
