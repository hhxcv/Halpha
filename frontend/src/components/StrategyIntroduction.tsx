import { Box, Typography } from "@mui/material";

import type { StrategySummary } from "../api/client";
import { surfaceFrameSx } from "../theme";


export default function StrategyIntroduction({
  strategy,
  embedded = false,
}: {
  strategy: StrategySummary;
  embedded?: boolean;
}) {
  return (
    <Box
      component="section"
      aria-label={`${strategy.display_name}策略介绍`}
      sx={embedded ? { pt: 1.5 } : { ...surfaceFrameSx, p: 2 }}
    >
      {!embedded && <>
        <Typography variant="overline" color="text.secondary">策略说明</Typography>
        <Typography variant="h2" sx={{ mt: .5, mb: 1.5 }}>{strategy.display_name}</Typography>
      </>}
      <Box component="dl" sx={{ m: 0, display: "grid", gap: 1.25 }}>
        {[
          ["价值逻辑", strategy.value_logic],
          ["适用场景", strategy.applicable_scenarios],
          ["执行行为", strategy.execution_behavior],
        ].map(([label, value]) => (
          <Box key={label} sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "88px minmax(0,1fr)" }, gap: .75 }}>
            <Typography component="dt" variant="caption" color="text.secondary" sx={{ pt: .2 }}>{label}</Typography>
            <Typography component="dd" variant="body2" sx={{ m: 0 }}>{value}</Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
