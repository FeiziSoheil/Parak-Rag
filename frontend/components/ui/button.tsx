import * as React from "react";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "outline" | "ghost" | "destructive";
  size?: "default" | "sm" | "icon" | "icon-sm";
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className = "", variant = "default", size = "default", ...props }, ref) => {
    const base =
      "inline-flex items-center justify-center rounded-xl text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:ring-offset-1 disabled:pointer-events-none disabled:opacity-50";
    const variants = {
      default:
        "bg-[var(--button)] text-[var(--button-foreground)] border border-[var(--button-border)] hover:bg-[var(--button-hover)]",
      outline:
        "border border-border bg-transparent hover:bg-muted text-foreground",
      ghost: "bg-transparent hover:bg-muted text-foreground",
      destructive:
        "bg-destructive/10 text-destructive hover:bg-destructive/15 text-foreground border border-transparent",
    };
    const sizes = {
      default: "h-9 px-4",
      sm: "h-8 px-3 text-xs",
      icon: "h-9 w-9",
      "icon-sm": "h-8 w-8",
    };
    return (
      <button
        ref={ref}
        className={`${base} ${variants[variant]} ${sizes[size]} ${className}`}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
export { Button };
