"use client";

import type { HTMLAttributes, ReactNode } from "react";

function tooltipTitle(content: ReactNode): string | undefined {
  if (typeof content === "string") {
    return content;
  }
  if (typeof content === "number") {
    return String(content);
  }
  return undefined;
}

export function Tooltip({
  children,
  content,
  ...props
}: {
  children: ReactNode;
  content?: ReactNode;
} & HTMLAttributes<HTMLSpanElement>) {
  const title = props.title ?? tooltipTitle(content);

  return (
    <span
      {...props}
      className={props.className}
      title={title}
    >
      {children}
    </span>
  );
}
