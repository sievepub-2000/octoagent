import { cn } from "@/lib/utils";

export function FlipDisplay({
  uniqueKey,
  children,
  className,
}: {
  uniqueKey: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("relative overflow-hidden", className)}>
      <div key={uniqueKey}>{children}</div>
    </div>
  );
}
