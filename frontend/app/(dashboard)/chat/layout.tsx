export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="h-screen flex flex-col bg-background relative overflow-hidden">
      <div className="gradient-mesh" aria-hidden />
      <div className="grain" aria-hidden />
      <div className="relative z-10 h-full">
        {children}
      </div>
    </div>
  );
}
