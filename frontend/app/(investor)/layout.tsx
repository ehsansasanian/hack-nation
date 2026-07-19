import { Nav } from "@/components/nav";

// Investor shell: the pipeline dashboard and everything downstream of it
// (sourcing, mandate, application detail, memo, founder profiles) share the
// left nav. The landing page and the founder-facing apply flow deliberately
// live outside this shell, so the investor nav never shows there.
export default function InvestorLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="flex min-h-screen">
      <Nav />
      <main className="min-w-0 flex-1 overflow-x-hidden">{children}</main>
    </div>
  );
}
