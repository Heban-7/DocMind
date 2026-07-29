export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="bg-background text-on-surface overflow-hidden h-screen flex font-body-md">
      {children}
    </div>
  );
}
