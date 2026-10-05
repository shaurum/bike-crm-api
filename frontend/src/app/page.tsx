"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Toaster } from "@/components/ui/toaster";
import { useAuthStore, useAuthReady } from "@/lib/store";
import { authApi } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/utils";
import { Bike, Users, DollarSign, AlertTriangle, Calendar, CheckCircle, Clock } from "lucide-react";

export default function DashboardPage() {
  const router = useRouter();
  const { user, accessToken, logout } = useAuthStore();
  const ready = useAuthReady();
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ready) return;
    if (!accessToken) {
      router.push("/login");
      return;
    }
    fetchStats();
  }, [ready, accessToken, router]);

  const fetchStats = async () => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/dashboard/stats?days=30`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const statCards = [
    { title: "Доступно байков", value: stats?.bikes?.available || 0, icon: Bike, color: "text-green-600", bg: "bg-green-100" },
    { title: "В аренде", value: stats?.bikes?.rented || 0, icon: Bike, color: "text-blue-600", bg: "bg-blue-100" },
    { title: "На обслуживании", value: stats?.bikes?.maintenance || 0, icon: AlertTriangle, color: "text-red-600", bg: "bg-red-100" },
    { title: "Выручка за 30 дней", value: formatCurrency(stats?.revenue || 0), icon: DollarSign, color: "text-emerald-600", bg: "bg-emerald-100" },
  ];

  if (loading) {
    return <div className="flex h-screen items-center justify-center">Загрузка...</div>;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white px-6 py-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Bike CRM</h1>
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-600">{user?.full_name}</span>
            <Button variant="ghost" size="sm" onClick={logout}>Выйти</Button>
          </div>
        </div>
      </header>

      <main className="p-6">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-8">
          {statCards.map((stat) => (
            <Card key={stat.title}>
              <CardContent className="flex items-center gap-4 p-6">
                <div className={`rounded-full p-3 ${stat.bg}`}>
                  <stat.icon className={`h-6 w-6 ${stat.color}`} />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">{stat.title}</p>
                  <p className="text-2xl font-bold">{stat.value}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 mb-8">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                Лиды за 30 дней
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span>Всего</span>
                  <span className="font-bold">{stats?.leads?.total || 0}</span>
                </div>
                <div className="flex justify-between">
                  <span>Новые</span>
                  <Badge variant="info">{stats?.leads?.new || 0}</Badge>
                </div>
                <div className="flex justify-between">
                  <span>Выиграли</span>
                  <Badge variant="success">{stats?.leads?.won || 0}</Badge>
                </div>
                <div className="flex justify-between">
                  <span>Конверсия</span>
                  <span className="font-bold">{stats?.leads?.conversion || 0}%</span>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Calendar className="h-5 w-5" />
                Брони за 30 дней
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span>Всего</span>
                  <span className="font-bold">{stats?.bookings?.total || 0}</span>
                </div>
                <div className="flex justify-between">
                  <span>Подтверждены</span>
                  <Badge variant="default">{stats?.bookings?.confirmed || 0}</Badge>
                </div>
                <div className="flex justify-between">
                  <span>Завершены</span>
                  <Badge variant="success">{stats?.bookings?.completed || 0}</Badge>
                </div>
                <div className="flex justify-between">
                  <span>Конверсия</span>
                  <span className="font-bold">{stats?.bookings?.conversion || 0}%</span>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock className="h-5 w-5" />
                Задачи
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span>К выполнению</span>
                  <Badge variant="secondary">{stats?.tasks?.pending || 0}</Badge>
                </div>
                <div className="flex justify-between">
                  <span>Просрочено</span>
                  <Badge variant="destructive">{stats?.tasks?.overdue || 0}</Badge>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Быстрые действия</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2 sm:grid-cols-2">
              <Button asChild>
                <a href="/leads">Новый лид</a>
              </Button>
              <Button asChild variant="outline">
                <a href="/bikes">Добавить байк</a>
              </Button>
              <Button asChild variant="outline">
                <a href="/bookings">Новая бронь</a>
              </Button>
              <Button asChild variant="outline">
                <a href="/customers">Новый клиент</a>
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Навигация</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2 sm:grid-cols-2">
              <Button asChild variant="outline">
                <a href="/leads">📥 Входящие лиды</a>
              </Button>
              <Button asChild variant="outline">
                <a href="/bikes">🚲 Флит</a>
              </Button>
              <Button asChild variant="outline">
                <a href="/bookings">📅 Брони</a>
              </Button>
              <Button asChild variant="outline">
                <a href="/tasks">✅ Задачи</a>
              </Button>
              <Button asChild variant="outline">
                <a href="/customers">👥 Клиенты</a>
              </Button>
              <Button asChild variant="outline">
                <a href="/dashboard">📊 Дашборд</a>
              </Button>
            </CardContent>
          </Card>
        </div>
      </main>

      <Toaster />
    </div>
  );
}