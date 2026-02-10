import * as React from "react";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className = "", type, ...props }, ref) => (
    <input
      type={type}
      className={`flex h-10 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:ring-offset-0 disabled:cursor-not-allowed disabled:opacity-50 transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium ${className}`}
      ref={ref}
      {...props}
    />
  )
);
Input.displayName = "Input";
export { Input };
