"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Brain, LayoutDashboard, Radar, SlidersHorizontal } from "lucide-react";

import { cn } from "@/lib/utils";

const ITEMS = [
  { href: "/pipeline", label: "Pipeline", icon: LayoutDashboard, match: (p: string) => p.startsWith("/pipeline") || p.startsWith("/applications") || p.startsWith("/founders") },
  { href: "/sourcing", label: "Sourcing", icon: Radar, match: (p: string) => p.startsWith("/sourcing") },
  { href: "/mandate", label: "Mandate", icon: SlidersHorizontal, match: (p: string) => p.startsWith("/mandate") },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-sidebar">
      <Link href="/" className="flex items-center gap-2 px-5 py-5">
        <span className="flex size-8 items-center justify-center rounded-lg bg-blue-600 text-white">
          <Brain className="size-4.5" />
        </span>
        <div className="leading-tight">
          <div className="text-sm font-semibold tracking-tight">The VC Brain</div>
          <div className="text-[0.7rem] text-muted-foreground">Venture funnel OS</div>
        </div>
      </Link>
      <nav className="flex flex-col gap-0.5 px-3 py-2">
        {ITEMS.map((item) => {
          const active = item.match(pathname);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-blue-50 text-blue-700"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <Icon className="size-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto px-5 py-4 text-[0.7rem] leading-relaxed text-muted-foreground">
        Sourcing → screening → diligence → decision.
      </div>
    </aside>
  );
}
