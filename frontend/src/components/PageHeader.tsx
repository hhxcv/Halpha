import { Box, Typography } from "@mui/material";

type PageHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
};

export default function PageHeader({ eyebrow, title, description }: PageHeaderProps) {
  return (
    <Box component="header" sx={{ mb: 2.5 }}>
      {eyebrow && <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontWeight: 700 }}>{eyebrow}</Typography>}
      <Typography variant="h1" sx={{ mt: eyebrow ? .25 : 0, mb: description ? .5 : 0 }}>{title}</Typography>
      {description && <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 680 }}>{description}</Typography>}
    </Box>
  );
}
