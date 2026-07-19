import Link from "next/link";
import { ArrowLeft, Brain } from "lucide-react";

// "Searching Investment" shell: the founder-facing apply flow. No investor
// nav here - just a slim brand bar with a way back to the landing page.
export default function SearchingLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b border-border px-6 py-3">
        <Link href="/" className="flex items-center gap-2">
          <span className="flex size-7 items-center justify-center rounded-lg bg-blue-600 text-white">
            <Brain className="size-4" />
          </span>
          <span className="text-sm font-semibold tracking-tight">The VC Brain</span>
        </Link>
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          Home
        </Link>
      </header>
      <main className="min-w-0 flex-1 overflow-x-hidden">{children}</main>
    </div>
  );
}
