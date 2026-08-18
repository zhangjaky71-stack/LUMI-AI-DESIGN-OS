"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Home", mark: "H" },
  { href: "/projects", label: "Projects", mark: "P" },
  { href: "/workspace", label: "Workspace", mark: "W" },
  { href: "/settings", label: "Settings", mark: "S" },
] as const;

export function AppNav() {
  const pathname = usePathname();
  return (
    <nav className="app-nav" aria-label="Primary navigation">
      <ul className="app-nav-list">
        {NAV_ITEMS.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                className="app-nav-link"
                aria-current={active ? "page" : undefined}
              >
                <span className="app-nav-mark" aria-hidden="true">
                  {item.mark}
                </span>
                <span>{item.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
