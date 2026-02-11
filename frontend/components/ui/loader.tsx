"use client";

import { cn } from "@/lib/utils";

const loaderVariants = {
  "dots-pulse": "dots-pulse",
  spinner: "spinner",
} as const;

type LoaderVariant = keyof typeof loaderVariants;

interface LoaderProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: LoaderVariant;
  size?: "sm" | "md" | "lg";
}

const sizeClasses = {
  sm: "loader-dots-pulse-sm",
  md: "loader-dots-pulse-md",
  lg: "loader-dots-pulse-lg",
};

function Loader({ variant = "dots-pulse", size = "sm", className, ...props }: LoaderProps) {
  if (variant === "dots-pulse") {
    return (
      <div
        role="status"
        aria-label="Loading"
        className={cn("inline-flex items-center gap-1 ", sizeClasses[size], className)}
        {...props}
      >
        <span className="loader-dot loader-dot-1" />
        <span className="loader-dot loader-dot-2" />
        <span className="loader-dot loader-dot-3" />
      </div>
    );
  }

  return null;
}

export { Loader };
