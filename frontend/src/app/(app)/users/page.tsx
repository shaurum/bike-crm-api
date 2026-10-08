"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Copy,
  KeyRound,
  Link2,
  Plus,
  ShieldCheck,
  Trash2,
  UserCheck,
  UserPlus,
  UserX,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { adminUsersApi, invitesApi, InviteRecord } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { toast } from "@/hooks/use-toast";

interface AdminUser {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  role: string;
  is_active: boolean;
  last_login: string | null;
  created_at: string;
}

const ROLE_LABELS: Record<string, string> = {
  admin: "Администратор",
  manager: "Менеджер",
  mechanic: "Механик",
};

function errText(err: unknown, fallback: string): string {
  const e = err as { response?: { data?: { detail?: unknown } } };
  const detail = e?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  return fallback;
}

/* ------------------------------------------------------------------ */
/* Пригласительные ссылки                                              */
/* ------------------------------------------------------------------ */

function inviteUrl(token: string): string {
  if (typeof window === "undefined") return `/register?invite=${token}`;
  return `${window.location.origin}/register?invite=${token}`;
}

const INVITE_STATUS: Record<string, { label: string; cls: string }> = {
  active: { label: "активно", cls: "bg-green-100 text-green-800" },
  used: { label: "использовано", cls: "bg-muted text-muted-foreground" },
  expired: { label: "истекло", cls: "bg-amber-50 text-amber-700" },
};

function InvitesSection() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ role: "manager", email: "", days: 14 });
  const [created, setCreated] = useState<InviteRecord | null>(null);

  const { data: invites } = useQuery({
    queryKey: ["admin-invites"],
    queryFn: async () => (await invitesApi.list()).data,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["admin-invites"] });

  const create = useMutation({
    mutationFn: async () =>
      (
        await invitesApi.create({
          role: form.role,
          email: form.email.trim() || undefined,
          days: form.days,
        })
      ).data,
    onSuccess: (invite) => {
      setCreated(invite);
      invalidate();
    },
    onError: (err) =>
      toast({ title: "Не удалось создать", description: errText(err, "Ошибка") }),
  });

  const revoke = async (id: string) => {
    try {
      await invitesApi.remove(id);
      toast({ title: "Приглашение отозвано" });
      invalidate();
    } catch (err) {
      toast({ title: "Не удалось отозвать", description: errText(err, "Ошибка") });
    }
  };

  const copy = async (token: string) => {
    try {
      await navigator.clipboard.writeText(inviteUrl(token));
      toast({ title: "Ссылка скопирована" });
    } catch {
      toast({ title: "Не удалось скопировать", description: inviteUrl(token) });
    }
  };

  const closeDialog = () => {
    setOpen(false);
    setCreated(null);
    setForm({ role: "manager", email: "", days: 14 });
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Приглашения</h2>
          <p className="text-sm text-muted-foreground">
            Ссылка открывает регистрацию новичка с выбранной ролью. Регистрация по
            прямому адресу закрыта.
          </p>
        </div>
        <Button onClick={() => setOpen(true)}>
          <Link2 className="mr-2 h-4 w-4" aria-hidden />
          Пригласить
        </Button>
      </div>

      <div className="overflow-hidden rounded-lg border bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-gray-50 text-left text-xs uppercase text-gray-500">
              <th className="px-4 py-2.5">Роль</th>
              <th className="px-4 py-2.5">Email</th>
              <th className="px-4 py-2.5">Действует до</th>
              <th className="px-4 py-2.5">Статус</th>
              <th className="px-4 py-2.5 text-right">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {!invites?.length && (
              <tr>
                <td colSpan={5} className="px-4 py-4 text-center text-muted-foreground">
                  Приглашений пока нет
                </td>
              </tr>
            )}
            {invites?.map((inv) => {
              const st = INVITE_STATUS[inv.status] || INVITE_STATUS.active;
              return (
                <tr key={inv.id}>
                  <td className="px-4 py-3 font-medium">
                    {ROLE_LABELS[inv.role] || inv.role}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{inv.email || "—"}</td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {new Date(inv.expires_at).toLocaleDateString("ru-RU", {
                      day: "2-digit",
                      month: "2-digit",
                      year: "2-digit",
                    })}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-0.5 text-xs ${st.cls}`}>
                      {st.label}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1.5">
                      {inv.status === "active" && (
                        <>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => copy(inv.token)}
                          >
                            <Copy className="mr-1.5 h-3.5 w-3.5" aria-hidden />
                            Ссылка
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => revoke(inv.id)}
                            title="Отозвать приглашение"
                          >
                            <Trash2 className="h-3.5 w-3.5" aria-hidden />
                          </Button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <Dialog open={open} onOpenChange={(v) => !v && closeDialog()}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {created ? "Ссылка-приглашение" : "Пригласить сотрудника"}
            </DialogTitle>
          </DialogHeader>

          {created ? (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Отправьте ссылку сотруднику — регистрация по ней откроет форму с ролью
                «{ROLE_LABELS[created.role] || created.role}».
              </p>
              <div className="flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2">
                <Link2 className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                <code className="min-w-0 flex-1 truncate text-xs">{inviteUrl(created.token)}</code>
              </div>
              <p className="text-xs text-muted-foreground">
                Действует до {new Date(created.expires_at).toLocaleDateString("ru-RU")}.
                Можно отозвать в списке.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <Select
                value={form.role}
                onValueChange={(role) => setForm({ ...form, role })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(ROLE_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                placeholder="Email (необязательно — ограничить приглашение)"
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
              <Select
                value={String(form.days)}
                onValueChange={(days) => setForm({ ...form, days: Number(days) })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="7">Действует 7 дней</SelectItem>
                  <SelectItem value="14">Действует 14 дней</SelectItem>
                  <SelectItem value="30">Действует 30 дней</SelectItem>
                  <SelectItem value="90">Действует 90 дней</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          <DialogFooter>
            {created ? (
              <>
                <Button variant="outline" onClick={() => copy(created.token)}>
                  <Copy className="mr-2 h-4 w-4" aria-hidden />
                  Копировать
                </Button>
                <Button onClick={closeDialog}>Готово</Button>
              </>
            ) : (
              <>
                <Button variant="outline" onClick={closeDialog}>
                  Отмена
                </Button>
                <Button
                  onClick={() => create.mutate()}
                  disabled={create.isPending}
                >
                  <UserPlus className="mr-2 h-4 w-4" aria-hidden />
                  {create.isPending ? "…" : "Создать ссылку"}
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function UsersPage() {
  const queryClient = useQueryClient();
  const me = useAuthStore((state) => state.user);
  const isAdmin = me?.role === "admin";

  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    phone: "",
    role: "manager",
  });
  const [resetFor, setResetFor] = useState<AdminUser | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["admin-users"],
    queryFn: async () => {
      const { data } = await adminUsersApi.list();
      return data as AdminUser[];
    },
    enabled: isAdmin,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["admin-users"] });

  const create = useMutation({
    mutationFn: async () => {
      await adminUsersApi.create({
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        password: form.password,
        phone: form.phone.trim() || undefined,
        role: form.role,
      });
    },
    onSuccess: () => {
      toast({ title: "Пользователь создан" });
      setCreateOpen(false);
      setForm({ full_name: "", email: "", password: "", phone: "", role: "manager" });
      invalidate();
    },
    onError: (err) =>
      toast({ title: "Не удалось создать", description: errText(err, "Ошибка") }),
  });

  const patchUser = async (id: string, payload: Record<string, unknown>, okTitle: string) => {
    setBusyId(id);
    try {
      await adminUsersApi.update(id, payload);
      toast({ title: okTitle });
      invalidate();
    } catch (err) {
      toast({ title: "Не удалось изменить", description: errText(err, "Ошибка") });
    } finally {
      setBusyId(null);
    }
  };

  const resetPassword = useMutation({
    mutationFn: async () => {
      if (!resetFor) return;
      await adminUsersApi.resetPassword(resetFor.id, newPassword);
    },
    onSuccess: () => {
      toast({ title: "Пароль сброшен" });
      setResetFor(null);
      setNewPassword("");
    },
    onError: (err) =>
      toast({ title: "Не удалось сбросить", description: errText(err, "Ошибка") }),
  });

  if (!isAdmin) {
    return (
      <div className="rounded-lg border bg-white p-8 text-center">
        <ShieldCheck className="mx-auto mb-2 h-8 w-8 text-muted-foreground" aria-hidden />
        <p className="text-sm text-muted-foreground">
          Раздел доступен только администратору
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Пользователи</h1>
          <p className="text-sm text-muted-foreground">
            Аккаунты, роли и сброс паролей. Самостоятельная регистрация закрыта.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" aria-hidden />
          Добавить
        </Button>
      </div>

      <div className="overflow-hidden rounded-lg border bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-gray-50 text-left text-xs uppercase text-gray-500">
              <th className="px-4 py-2.5">Сотрудник</th>
              <th className="px-4 py-2.5">Роль</th>
              <th className="px-4 py-2.5">Статус</th>
              <th className="px-4 py-2.5">Был в системе</th>
              <th className="px-4 py-2.5 text-right">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {isLoading && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">
                  Загрузка…
                </td>
              </tr>
            )}
            {data?.map((u) => {
              const isMe = u.id === me?.id;
              return (
                <tr key={u.id} className={u.is_active ? "" : "opacity-60"}>
                  <td className="px-4 py-3">
                    <p className="font-medium">
                      {u.full_name}
                      {isMe && (
                        <span className="ml-2 text-xs text-muted-foreground">(вы)</span>
                      )}
                    </p>
                    <p className="text-xs text-muted-foreground">{u.email}</p>
                  </td>
                  <td className="px-4 py-3">
                    <Select
                      value={u.role}
                      disabled={isMe || busyId === u.id}
                      onValueChange={(role) =>
                        patchUser(u.id, { role }, "Роль обновлена")
                      }
                    >
                      <SelectTrigger className="h-8 w-40 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(ROLE_LABELS).map(([value, label]) => (
                          <SelectItem key={value} value={value}>
                            {label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={u.is_active ? "secondary" : "outline"}>
                      {u.is_active ? "активен" : "отключён"}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {u.last_login
                      ? new Date(u.last_login).toLocaleString("ru-RU", {
                          day: "2-digit",
                          month: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : "не входил"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1.5">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setResetFor(u);
                          setNewPassword("");
                        }}
                        title="Сбросить пароль"
                      >
                        <KeyRound className="mr-1.5 h-3.5 w-3.5" aria-hidden />
                        Пароль
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={isMe || busyId === u.id}
                        onClick={() =>
                          patchUser(
                            u.id,
                            { is_active: !u.is_active },
                            u.is_active ? "Пользователь отключён" : "Пользователь активирован"
                          )
                        }
                        title={u.is_active ? "Деактивировать" : "Активировать"}
                      >
                        {u.is_active ? (
                          <UserX className="mr-1.5 h-3.5 w-3.5" aria-hidden />
                        ) : (
                          <UserCheck className="mr-1.5 h-3.5 w-3.5" aria-hidden />
                        )}
                        {u.is_active ? "Отключить" : "Включить"}
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <InvitesSection />

      {/* Создание пользователя */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Новый пользователь</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder="ФИО"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />
            <Input
              placeholder="Email (логин)"
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
            <Input
              placeholder="Телефон (необязательно)"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
            <Input
              placeholder="Пароль (от 8 символов)"
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
            <Select
              value={form.role}
              onValueChange={(role) => setForm({ ...form, role })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(ROLE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Отмена
            </Button>
            <Button
              onClick={() => create.mutate()}
              disabled={
                create.isPending ||
                !form.full_name.trim() ||
                !form.email.trim() ||
                form.password.length < 8
              }
            >
              {create.isPending ? "…" : "Создать"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Сброс пароля */}
      <Dialog open={Boolean(resetFor)} onOpenChange={(v) => !v && setResetFor(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Сброс пароля</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {resetFor?.full_name} · {resetFor?.email}
          </p>
          <Input
            placeholder="Новый пароль (от 8 символов)"
            type="password"
            autoFocus
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && newPassword.length >= 8)
                resetPassword.mutate();
            }}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setResetFor(null)}>
              Отмена
            </Button>
            <Button
              onClick={() => resetPassword.mutate()}
              disabled={resetPassword.isPending || newPassword.length < 8}
            >
              {resetPassword.isPending ? "…" : "Сбросить"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
