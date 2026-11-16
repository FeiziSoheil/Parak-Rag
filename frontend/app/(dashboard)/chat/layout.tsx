import { CartProvider } from "@/contexts/CartContext";

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <CartProvider>
      <div className="h-screen flex flex-col bg-muted/40 dark:bg-background relative overflow-hidden">
        <div className="gradient-mesh" aria-hidden />
        <div className="grain" aria-hidden />
        <div className="relative z-10 h-full min-h-0">{children}</div>
      </div>
    </CartProvider>
  );
}
