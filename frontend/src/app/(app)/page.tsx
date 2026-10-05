"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/toaster";
import { dashboardApi } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import {
  Bike,
  Users,
  DollarSign,
  AlertTriangle,
  Calendar,
  Clock,
  ClipboardList,
  FileText,
} from "lucide-react";

export default function DashboardPage() {
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    dashboardApi
      .stats(30)
      .then((res) => {
        if (!cancelled) setStats(res.data);
      })
      .catch(() => {
        /* interceptor разберётся с 401 */
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <p className="text-sm text-muted-foreground">Загрузка…</p>
      </div>
    );
  }

  const statCards = [
    {
      title: "Доступно байков",
      value: stats?.bikes?.available || 0,
      icon: Bike,
      color: "text-green-600",
      bg: "bg-green-100",
    },
    {
      title: "В аренде",
      value: stats?.bikes?.rented || 0,
      icon: Bike,
      color: "text-blue-600",
      bg: "bg-blue-100",
    },
    {
      title: "На обслуживании",
      value: stats?.bikes?.maintenance || 0,
      icon: AlertTriangle,
      color: "text-red-600",
      bg: "bg-red-100",
    },
    {
      title: "Выручка за 30 дней",
      value: formatCurrency(stats?.revenue || 0),
      icon: DollarSign,
      color: "text-emerald-600",
      bg: "bg-emerald-100",
    },
  ];

  const quickLinks = [
    { href: "/orders", label: "Новый заказ", icon: ClipboardList },
    { href: "/customers", label: "Новый клиент", icon: Users },
    { href: "/parking", label: "Добавить байк", icon: Bike },
    { href: "/documents", label: "Документы", icon: FileText },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Панель управления</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Сводка по прокату за последние 30 дней
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {statCards.map((card) => (
          <Card key={card.title}>
            <CardContent className="flex items-center gap-4 p-6">
              <div className={`rounded-full p-3 ${card.bg}`}>
                <card.icon className={`h-6 w-6 ${card.color}`} aria-hidden />
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm text-muted-foreground">{card.title}</p>
                <p className="text-2xl font-bold">{card.value}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <Card>
          <CardHeader className="flex-row items-center gap-2 space-y-0">
            <Users className="h-5 w-5" aria-hidden />
            <CardTitle className="text-base">Лиды за 30 дней</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex justify-between text-sm">
              <span>Всего</span>
              <span className="font-bold">{stats?.leads?.total || 0}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span>Новые</span>
              <Badge variant="info">{stats?.leads?.new || 0}</Badge>
            </div>
            <div className="flex justify-between text-sm">
              <span>Выиграли</span>
              <Badge variant="success">{stats?.leads?.won || 0}</Badge>
            </div>
            <div className="flex justify-between text-sm">
              <span>Конверсия</span>
              <span className="font-bold">{stats?.leads?.conversion || 0}%</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center gap-2 space-y-0">
            <Calendar className="h-5 w-5" aria-hidden />
            <CardTitle className="text-base">Брони за 30 дней</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex justify-between text-sm">
              <span>Всего</span>
              <span className="font-bold">{stats?.bookings?.total || 0}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span>Подтверждены</span>
              <Badge>{stats?.bookings?.confirmed || 0}</Badge>
            </div>
            <div className="flex justify-between text-sm">
              <span>Завершены</span>
              <Badge variant="success">{stats?.bookings?.completed || 0}</Badge>
            </div>
            <div className="flex justify-between text-sm">
              <span>Конверсия</span>
              <span className="font-bold">{stats?.bookings?.conversion || 0}%</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center gap-2 space-y-0">
            <Clock className="h-5 w-5" aria-hidden />
            <CardTitle className="text-base">Задачи</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex justify-between text-sm">
              <span>К выполнению</span>
              <Badge variant="secondary">{stats?.tasks?.pending || 0}</Badge>
            </div>
            <div className="flex justify-between text-sm">
              <span>Просрочено</span>
              <Badge variant="destructive">{stats?.tasks?.overdue || 0}</Badge>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Быстрые действия</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {quickLinks.map((link) => (
            <Button key={link.href} asChild variant="outline" className="justify-start gap-2">
              <Link href={link.href}>
                <link.icon className="h-4 w-4" aria-hidden />
                {link.label}
              </Link>
            </Button>
          ))}
        </CardContent>
      </Card>

      <Toaster />
    </div>
  );
}