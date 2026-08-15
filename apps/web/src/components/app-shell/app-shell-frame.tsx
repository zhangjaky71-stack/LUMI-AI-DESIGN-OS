"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import styles from "./app-shell-frame.module.css";
import { useShell } from "./shell-context";

const NAVIGATION = [
  { href: "/app/projects", label: "项目", flag: "projects" },
  { href: "/app/brands", label: "品牌", flag: "brands" },
  { href: "/app/assets", label: "素材", flag: "assets" },
  { href: "/app/team", label: "团队", flag: "team" },
  { href: "/app/billing", label: "用量", flag: "billing" },
  { href: "/app/settings", label: "设置", flag: null },
] as const;

function subscribeOnlineStatus(onStoreChange: () => void): () => void {
  window.addEventListener("online", onStoreChange);
  window.addEventListener("offline", onStoreChange);
  return () => {
    window.removeEventListener("online", onStoreChange);
    window.removeEventListener("offline", onStoreChange);
  };
}

function getOnlineSnapshot(): boolean {
  return navigator.onLine;
}

function getServerOnlineSnapshot(): boolean {
  return true;
}

export function AppShellFrame({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();
  const online = useSyncExternalStore(
    subscribeOnlineStatus,
    getOnlineSnapshot,
    getServerOnlineSnapshot,
  );
  const {
    session,
    activeOrganization,
    flags,
    switchOrganization,
    commandPaletteOpen,
    setCommandPaletteOpen,
  } = useShell();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  const openCommandPalette = useCallback(() => {
    if (flags.commandPalette) setCommandPaletteOpen(true);
  }, [flags.commandPalette, setCommandPaletteOpen]);

  const closeCommandPalette = useCallback(() => {
    setCommandPaletteOpen(false);
    requestAnimationFrame(() => triggerRef.current?.focus());
  }, [setCommandPaletteOpen]);

  useEffect(() => {
    if (commandPaletteOpen) inputRef.current?.focus();
  }, [commandPaletteOpen]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (
        flags.commandPalette &&
        (event.metaKey || event.ctrlKey) &&
        event.key.toLowerCase() === "k"
      ) {
        event.preventDefault();
        openCommandPalette();
      } else if (event.key === "Escape" && commandPaletteOpen) {
        event.preventDefault();
        closeCommandPalette();
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [
    closeCommandPalette,
    commandPaletteOpen,
    flags.commandPalette,
    openCommandPalette,
  ]);

  const trapDialogFocus = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Tab") return;
    if (event.shiftKey && document.activeElement === inputRef.current) {
      event.preventDefault();
      closeRef.current?.focus();
    } else if (
      !event.shiftKey &&
      document.activeElement === closeRef.current
    ) {
      event.preventDefault();
      inputRef.current?.focus();
    }
  };

  return (
    <div className="lumi-app-shell">
      <a className="skip-link" href="#main-content">
        跳到主要内容
      </a>
      <aside className="lumi-sidebar" aria-label="产品导航栏">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">
            L
          </span>
          <span>LUMI</span>
        </div>
        <nav className="nav-stack" aria-label="主导航">
          {NAVIGATION.filter(
            (item) => item.flag === null || flags[item.flag],
          ).map((item) => {
            const active =
              pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                className="nav-item"
                data-active={active ? "true" : "false"}
                aria-current={active ? "page" : undefined}
                href={item.href}
              >
                <span className="nav-dot" aria-hidden="true" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          <span className="status-dot" aria-hidden="true" />
          <span>Architecture V2</span>
        </div>
      </aside>

      <div className="lumi-shell-body">
        <header className="lumi-topbar">
          <div className="organization-control">
            <label className="sr-only" htmlFor="organization-switcher">
              切换组织
            </label>
            <select
              id="organization-switcher"
              aria-label="切换组织"
              value={activeOrganization.id}
              onChange={(event) => switchOrganization(event.target.value)}
            >
              {session.organizations.map((organization) => (
                <option key={organization.id} value={organization.id}>
                  {organization.name}
                </option>
              ))}
            </select>
            <span className="role-pill">{activeOrganization.role}</span>
          </div>
          <div className="topbar-actions">
            {flags.commandPalette ? (
              <button
                ref={triggerRef}
                className="command-trigger"
                type="button"
                onClick={openCommandPalette}
                aria-label="打开命令面板"
                aria-haspopup="dialog"
                aria-expanded={commandPaletteOpen}
              >
                搜索
                <kbd>⌘K</kbd>
              </button>
            ) : null}
            <div
              className="avatar"
              aria-label={`当前用户 ${session.user.display_name}`}
              title={session.user.display_name}
            >
              {session.user.display_name.slice(0, 1).toUpperCase()}
            </div>
          </div>
        </header>
        {!online ? (
          <div className={styles.offlineBanner} role="status">
            当前处于离线状态。已加载内容可继续查看，网络恢复后再重试服务端操作。
          </div>
        ) : null}
        <main id="main-content" className="lumi-main" tabIndex={-1}>
          {children}
        </main>
      </div>

      {flags.commandPalette && commandPaletteOpen ? (
        <div className="command-backdrop">
          <div
            className="command-dialog"
            role="dialog"
            aria-modal="true"
            aria-label="命令面板"
            onKeyDown={trapDialogFocus}
          >
            <div className="command-row">
              <input
                ref={inputRef}
                aria-label="搜索命令"
                placeholder="搜索项目、命令或素材…"
              />
              <button
                ref={closeRef}
                type="button"
                onClick={closeCommandPalette}
                aria-label="关闭命令面板"
              >
                Esc
              </button>
            </div>
            <div className="command-empty">
              输入关键词开始搜索。后续工作区命令会在这里统一注册。
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
