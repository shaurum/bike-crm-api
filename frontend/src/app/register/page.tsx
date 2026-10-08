"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Toaster } from "@/components/ui/toaster";
import { Bike, Link2, Lock } from "lucide-react";
import { authApi, invitesApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";

const ROLE_LABELS: Record<string, string> = {
  admin: "Администратор",
  manager: "Менеджер",
  mechanic: "Механик",
};

type InviteState =
  | { kind: "checking" }
  | { kind: "valid"; role: string }
  | { kind: "invalid"; detail: string }
  | null;

export default function RegisterPage() {
  const router = useRouter();
  const setAuth = useAuthStore((state) => state.setAuth);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [invite, setInvite] = useState<InviteState>(null);
  const [inviteToken, setInviteToken] = useState<string | null>(null);
  const [registerOpen, setRegisterOpen] = useState(false);
  const [statusChecked, setStatusChecked] = useState(false);
  const bootstrapped = useRef(false);

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;

    const token = new URLSearchParams(window.location.search).get("invite");
    authApi
      .registerStatus()
      .then((res) => setRegisterOpen(Boolean(res.data?.open)))
      .catch(() => setRegisterOpen(false))
      .finally(() => setStatusChecked(true));

    if (token) {
      setInviteToken(token);
      setInvite({ kind: "checking" });
      invitesApi
        .validate(token)
        .then((res) => {
          if (res.data.ok && res.data.role) {
            setInvite({ kind: "valid", role: res.data.role });
          } else {
            setInvite({
              kind: "invalid",
              detail: res.data.detail || "Приглашение недействительно",
            });
          }
        })
        .catch(() =>
          setInvite({ kind: "invalid", detail: "Не удалось проверить приглашение" })
        );
    }
  }, []);

  const inviteOk = invite?.kind === "valid";
  const canShowForm = inviteOk || registerOpen;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Пароли не совпадают");
      return;
    }

    if (password.length < 8) {
      setError("Пароль должен быть минимум 8 символов");
      return;
    }

    setLoading(true);

    try {
      await authApi.register({
        email,
        password,
        full_name: fullName,
        phone,
        invite_token: inviteToken || undefined,
      });
      const loginRes = await authApi.login(email, password);
      const { access_token, refresh_token } = loginRes.data;
      useAuthStore.getState().setTokens(access_token, refresh_token);
      const meRes = await authApi.me();
      setAuth(meRes.data, access_token, refresh_token);
      router.push("/");
      router.refresh();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Ошибка регистрации");
    } finally {
      setLoading(false);
    }
  };

  const waiting = !statusChecked || invite?.kind === "checking";

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary">
            <Bike className="h-7 w-7 text-primary-foreground" />
          </div>
          <CardTitle>Регистрация</CardTitle>
          <CardDescription>
            {inviteOk
              ? "Вы приглашены в команду — заполните данные"
              : registerOpen
                ? "Первый аккаунт станет администратором"
                : "Создание аккаунтов в Bike CRM"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {waiting && (
            <p className="text-center text-sm text-muted-foreground">Проверяем приглашение…</p>
          )}

          {!waiting && invite && invite.kind === "invalid" && (
            <div className="space-y-4">
              <div className="rounded-md bg-amber-50 p-3 text-sm text-amber-800">
                <p className="flex items-center gap-2 font-medium">
                  <Lock className="h-4 w-4" />
                  {invite.detail}
                </p>
                <p className="mt-1 text-xs">
                  Попросите у администратора новую ссылку-приглашение.
                </p>
              </div>
            </div>
          )}

          {!waiting && (!invite || inviteOk) && !registerOpen && invite?.kind !== "valid" ? (
            <div className="rounded-md bg-muted p-3 text-sm text-muted-foreground">
              Регистрация закрыта — аккаунт создаёт администратор или по ссылке-приглашению.
            </div>
          ) : null}

          {canShowForm && (
            <form onSubmit={handleSubmit} className="space-y-4" autoComplete="on">
              {error && (
                <div className="rounded-md bg-red-50 p-3 text-sm text-red-600">{error}</div>
              )}
              {inviteOk && (
                <div className="flex items-center gap-2 rounded-md bg-green-50 px-3 py-2 text-xs text-green-800">
                  <Link2 className="h-3.5 w-3.5" />
                  Приглашение: {ROLE_LABELS[invite.role] || invite.role}
                </div>
              )}
              <div className="space-y-2">
                <label htmlFor="full_name" className="text-sm font-medium">ФИО</label>
                <Input
                  id="full_name"
                  name="name"
                  type="text"
                  autoComplete="name"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Иван Иванов"
                  required
                  disabled={loading}
                />
              </div>
              <div className="space-y-2">
                <label htmlFor="email" className="text-sm font-medium">Email</label>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="employee@bike-crm.ru"
                  required
                  disabled={loading}
                />
              </div>
              <div className="space-y-2">
                <label htmlFor="phone" className="text-sm font-medium">Телефон</label>
                <Input
                  id="phone"
                  name="tel"
                  type="tel"
                  autoComplete="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="+7 (999) 123-45-67"
                  disabled={loading}
                />
              </div>
              <div className="space-y-2">
                <label htmlFor="password" className="text-sm font-medium">Пароль</label>
                <Input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  disabled={loading}
                  minLength={8}
                />
              </div>
              <div className="space-y-2">
                <label htmlFor="confirm_password" className="text-sm font-medium">Подтвердите пароль</label>
                <Input
                  id="confirm_password"
                  name="confirm-password"
                  type="password"
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  disabled={loading}
                  minLength={8}
                />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Регистрация..." : "Зарегистрироваться"}
              </Button>
            </form>
          )}
        </CardContent>
        <CardFooter className="flex flex-col gap-2">
          <p className="text-sm text-muted-foreground text-center">
            Уже есть аккаунт?{" "}
            <Link href="/login" className="text-primary hover:underline">
              Войти
            </Link>
          </p>
        </CardFooter>
      </Card>
      <Toaster />
    </div>
  );
}
