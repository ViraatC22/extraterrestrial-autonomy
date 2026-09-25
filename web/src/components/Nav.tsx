"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "MISSION CONTROL" },
  { href: "/inspector", label: "AUTONOMY INSPECTOR" },
  { href: "/scenario", label: "SCENARIO LAB" },
  { href: "/experiments", label: "EXPERIMENTS" },
  { href: "/failures", label: "FAILURE ANALYSIS" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-1 border-b border-white/10 bg-[#0b0e14] px-3 py-1.5">
      <span className="mr-4 font-mono text-[12px] font-semibold tracking-[0.3em] text-slate-100">
        EXONAUT
      </span>
      {LINKS.map((link) => {
        const active = pathname === link.href;
        return (
          <Link
            key={link.href}
            href={link.href}
            className={`rounded-sm px-2.5 py-1 font-mono text-[9px] tracking-[0.16em] transition ${
              active
                ? "bg-orange-500/15 text-orange-300"
                : "text-slate-500 hover:text-slate-200"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
