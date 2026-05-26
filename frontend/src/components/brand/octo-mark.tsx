import Image from "next/image";

import { cn } from "@/lib/utils";

type BaseProps = {
  className?: string;
  priority?: boolean;
  size?: number;
  avatarUrl?: string | null;
};

export function BrandMark({ className, priority = false, size = 44 }: BaseProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden bg-transparent shadow-none",
        className,
      )}
      style={{ height: size, width: size }}
    >
      <Image
        alt="OctoAgent"
        className="object-contain drop-shadow-[0_10px_18px_var(--emboss-shadow)]"
        fill
        fetchPriority={priority ? "high" : "auto"}
        loading={priority ? "eager" : "lazy"}
        sizes={`${size}px`}
        src="/images/octobot-user-transparent.png"
      />
    </div>
  );
}

export function AgentAvatar({ className, priority = false, size = 40, avatarUrl }: BaseProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-[1.1rem] border border-border/30 bg-[radial-gradient(circle_at_top,_var(--panel-start),_var(--panel-end)_60%)] shadow-[0_4px_10px_var(--emboss-shadow)]",
        className,
      )}
      style={{ height: size, width: size }}
    >
      {avatarUrl ? (
        <img
          alt="Agent avatar"
          className="absolute inset-0 size-full object-cover"
          src={avatarUrl}
          width={size}
          height={size}
        />
      ) : (
        <Image
          alt="OctoAgent assistant"
          className="object-contain p-[10%]"
          fill
          fetchPriority={priority ? "high" : "auto"}
          loading={priority ? "eager" : "lazy"}
          sizes={`${size}px`}
          src="/images/octobot-user-transparent.png"
        />
      )}
    </div>
  );
}

export function WelcomeArtwork({ className, priority = false }: Omit<BaseProps, "size">) {
  return (
    <div
      className={cn(
        "relative aspect-square w-full max-w-[168px] overflow-visible bg-transparent",
        className,
      )}
    >
      <Image
        alt="OctoAgent welcome artwork"
        className="object-contain drop-shadow-[0_20px_30px_var(--emboss-shadow)]"
        fill
        fetchPriority={priority ? "high" : "auto"}
        loading={priority ? "eager" : "lazy"}
        sizes="(max-width: 768px) 156px, 168px"
        src="/images/octobot-user-transparent.png"
      />
    </div>
  );
}

export function OctoPixelMark({ className, size = 28 }: Omit<BaseProps, "priority" | "avatarUrl">) {
  return (
    <div
      className={cn("inline-flex items-center justify-center rounded-md bg-transparent", className)}
      style={{ height: size, width: size }}
    >
      <svg
        aria-hidden="true"
        className="size-full"
        shapeRendering="crispEdges"
        viewBox="0 0 16 16"
        xmlns="http://www.w3.org/2000/svg"
      >
        <rect fill="#241527" height="1" width="8" x="4" y="2" />
        <rect fill="#241527" height="1" width="10" x="3" y="3" />
        <rect fill="#241527" height="1" width="12" x="2" y="4" />
        <rect fill="#241527" height="1" width="12" x="2" y="5" />
        <rect fill="#241527" height="1" width="12" x="2" y="6" />
        <rect fill="#241527" height="1" width="10" x="3" y="7" />
        <rect fill="#241527" height="1" width="2" x="2" y="8" />
        <rect fill="#241527" height="1" width="2" x="5" y="8" />
        <rect fill="#241527" height="1" width="2" x="9" y="8" />
        <rect fill="#241527" height="1" width="2" x="12" y="8" />
        <rect fill="#241527" height="2" width="1" x="3" y="9" />
        <rect fill="#241527" height="2" width="1" x="6" y="9" />
        <rect fill="#241527" height="2" width="1" x="9" y="9" />
        <rect fill="#241527" height="2" width="1" x="12" y="9" />
        <rect fill="#241527" height="1" width="1" x="4" y="11" />
        <rect fill="#241527" height="1" width="1" x="7" y="11" />
        <rect fill="#241527" height="1" width="1" x="8" y="11" />
        <rect fill="#241527" height="1" width="1" x="11" y="11" />

        <rect fill="#f18b4d" height="1" width="6" x="5" y="3" />
        <rect fill="#f18b4d" height="1" width="8" x="4" y="4" />
        <rect fill="#f18b4d" height="1" width="8" x="4" y="5" />
        <rect fill="#f18b4d" height="1" width="8" x="4" y="6" />
        <rect fill="#f18b4d" height="1" width="6" x="5" y="7" />
        <rect fill="#f18b4d" height="1" width="1" x="3" y="8" />
        <rect fill="#f18b4d" height="1" width="1" x="6" y="8" />
        <rect fill="#f18b4d" height="1" width="1" x="9" y="8" />
        <rect fill="#f18b4d" height="1" width="1" x="12" y="8" />
        <rect fill="#f18b4d" height="1" width="1" x="3" y="10" />
        <rect fill="#f18b4d" height="1" width="1" x="6" y="10" />
        <rect fill="#f18b4d" height="1" width="1" x="9" y="10" />
        <rect fill="#f18b4d" height="1" width="1" x="12" y="10" />

        <rect fill="#ffd2b0" height="1" width="3" x="6" y="4" />
        <rect fill="#ffd2b0" height="1" width="4" x="5" y="5" />
        <rect fill="#ffd2b0" height="1" width="2" x="5" y="6" />

        <rect fill="#241527" height="1" width="1" x="6" y="5" />
        <rect fill="#241527" height="1" width="1" x="9" y="5" />
        <rect fill="#241527" height="1" width="2" x="7" y="7" />
      </svg>
    </div>
  );
}