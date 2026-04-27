export function InspectorMetric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string | number;
  detail?: string | null;
}) {
  return (
    <div className="rounded-xl border border-border/60 bg-muted/15 px-3 py-3">
      <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground/80">
        {label}
      </div>
      <div className="mt-1 text-sm font-semibold text-foreground">{value}</div>
      {detail ? <div className="mt-1 text-xs text-muted-foreground">{detail}</div> : null}
    </div>
  );
}

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-3xl border border-dashed border-border/80 bg-muted/10 px-5 py-10 text-center">
      <div className="text-sm font-semibold text-foreground">{title}</div>
      <div className="mt-2 text-sm text-muted-foreground">{description}</div>
    </div>
  );
}
