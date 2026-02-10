import * as React from "react";

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className = "", ...props }, ref) => (
    <textarea
      ref={ref}
      className={`flex min-h-[80px] w-full rounded-xl border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-0 focus-visible:border-transparent disabled:cursor-not-allowed disabled:opacity-50 transition-colors resize-none ${className}`}
      {...props}
    />
  )
);
Textarea.displayName = "Textarea";
export { Textarea };
