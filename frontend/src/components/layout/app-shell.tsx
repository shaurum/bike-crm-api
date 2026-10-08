"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Bike, LogOut, Menu, User as UserIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { useAuthStore, useAuthReady } from "@/lib/store";
import { api, authApi } from "@/lib/api";
import { NAV_ITEMS } from "@/components/layout/nav-items";
import { HealthStatus } from "@/components/layout/health-status";
import { cn } from "@/lib/utils";

function isActiveRoute(href: string, pathname: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** Сколько непрочитанных сообщений по всем диалогам. */
function useUnreadTotal() {
  const { data } = useQuery({
    queryKey: ["conversations", "unread-total"],
    queryFn: async () => {
      const { data } = await api.get<
        { unread_count?: number }[]
      >("/conversations");
      return data;
    },
    refetchInterval: 30000,
    retry: false,
  });
  if (!Array.isArray(data)) return 0;
  return data.reduce((sum, item) => sum + (item.unread_count || 0), 0);
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const unread = useUnreadTotal();
  const role = useAuthStore((state) => state.user?.role);
  const items = NAV_ITEMS.filter(
    (item) => !item.adminOnly || role === "admin"
  );

  return (
    <nav className="flex flex-col gap-1">
      {items.map((item) => {
        const active = isActiveRoute(item.href, pathname);
        const Icon = item.icon;
        const showBadge = item.href === "/messages" && unread > 0;

        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
              active
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-gray-700 hover:bg-gray-100"
            )}
          >
            <Icon className="h-5 w-5 shrink-0" aria-hidden />
            <span className="truncate">{item.label}</span>
            {showBadge && (
              <span className="ml-auto inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-red-500 px-1.5 text-[11px] font-semibold text-white">
                {unread > 99 ? "99+" : unread}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2 px-3 py-1">
      <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-primary-foreground">
        <Bike className="h-5 w-5" aria-hidden />
      </span>
      <span className="text-lg font-bold leading-tight">Bike CRM</span>
    </Link>
  );
}

function UserPanel({ onNavigate }: { onNavigate?: () => void }) {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  const handleLogout = () => {
    onNavigate?.();
    logout();
    router.push("/login");
  };

  return (
    <div className="border-t border-gray-200 p-3">
      <div className="mb-2 flex items-center gap-2 px-2 py-1.5">
        <UserIcon className="h-4 w-4 shrink-0 text-gray-500" aria-hidden />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-gray-800">
            {user?.full_name ?? "Пользователь"}
          </p>
          <p className="truncate text-xs text-gray-500">{user?.email ?? ""}</p>
        </div>
      </div>
      <Button
        variant="outline"
        size="sm"
        className="w-full justify-start gap-2"
        onClick={handleLogout}
      >
        <LogOut className="h-4 w-4" aria-hidden />
        Выйти
      </Button>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const ready = useAuthReady();
  const hasToken = useAuthStore((state) => Boolean(state.accessToken));
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (ready && !hasToken) router.push("/login");
  }, [ready, hasToken, router]);

  useEffect(() => {
    if (!ready) return;
    if (!hasToken) return;
    authApi
      .me()
      .then((res) => useAuthStore.getState().updateUser(res.data))
      .catch(() => {
        /* interceptor освежит токен или выкинет на /login */
      });
  }, [ready, hasToken]);

  if (!ready || !hasToken) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <p className="text-sm text-gray-500">Загрузка…</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-gray-200 bg-white lg:flex">
        <div className="flex h-16 items-center border-b border-gray-200">
          <Brand />
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          <NavLinks />
        </div>
        <div className="border-t border-gray-200 p-3">
          <HealthStatus />
        </div>
        <UserPanel />
      </aside>

      {/* Mobile topbar */}
      <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-3 border-b border-gray-200 bg-white px-4 lg:hidden">
        <Brand />
        <Button
          variant="outline"
          size="icon"
          aria-label="Открыть меню"
          onClick={() => setMenuOpen(true)}
        >
          <Menu className="h-5 w-5" aria-hidden />
        </Button>
      </header>

      {/* Mobile drawer */}
      <Dialog open={menuOpen} onOpenChange={setMenuOpen}>
        <DialogContent
          className="!left-0 !top-0 !h-full !w-72 !max-w-[85vw] !translate-x-0 !translate-y-0 !gap-0 !rounded-none !border-r !p-0 flex flex-col"
          aria-describedby={undefined}
        >
          <DialogTitle className="sr-only">Меню навигации</DialogTitle>
          <div className="flex h-16 shrink-0 items-center border-b border-gray-200">
            <Brand />
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            <NavLinks onNavigate={() => setMenuOpen(false)} />
          </div>
          <div className="border-t border-gray-200 p-3">
            <HealthStatus />
          </div>
          <UserPanel onNavigate={() => setMenuOpen(false)} />
        </DialogContent>
      </Dialog>

      {/* Content */}
      <div className="lg:pl-64">
        <main className="p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}