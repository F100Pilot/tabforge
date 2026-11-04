"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Nova tablatura", match: (p: string) => p === "/" },
  { href: "/tabs", label: "As minhas tabs", match: (p: string) => p === "/tabs" },
];

export function SideNav() {
  const pathname = usePathname();
  return (
    <header className="sidenav">
      <Link href="/" className="logo">
        <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          {[5, 10, 15, 20].map((y) => (
            <line key={y} x1="2" x2="22" y1={y} y2={y} stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" />
          ))}
        </svg>
        TabForge
      </Link>
      <nav aria-label="Principal">
        <ul>
          {LINKS.map((l) => {
            const current = l.match(pathname);
            return (
              <li key={l.href}>
                <Link href={l.href} className="navlink" aria-current={current ? "page" : undefined}>
                  {l.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </header>
  );
}
