"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  CheckCircle2,
  Inbox,
  KeyRound,
  Mail,
  Plug,
  Power,
  Save,
  UserRound,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "@/hooks/use-toast";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type TabKey = "general" | "account" | "integrations";

const TABS: { key: TabKey; label: string; icon: typeof Building2 }[] = [
  { key: "general", label: "Основное", icon: Building2 },
  { key: "account", label: "Аккаунт", icon: UserRound },
  { key: "integrations", label: "Интеграции", icon: Plug },
];

/* ---------- Реквизиты арендодателя ---------- */

interface CompanyProfile {
  name: string;
  ogrnip: string | null;
  inn: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  return_address: string | null;
  age_restriction: string | null;
  deposit_return: string | null;
  photo_consent: string | null;
}

const COMPANY_FIELDS: {
  key: keyof CompanyProfile;
  label: string;
  placeholder?: string;
  wide?: boolean;
}[] = [
  { key: "name", label: "Наименование / ФИО", placeholder: "ИП Иванов Иван Иванович" },
  { key: "ogrnip", label: "ОГРНИП / ОГРН", placeholder: "123456789012345" },
  { key: "inn", label: "ИНН", placeholder: "123456789012" },
  { key: "phone", label: "Телефон", placeholder: "+7 900 000-00-00" },
  { key: "email", label: "Email", placeholder: "mail@example.com" },
  { key: "address", label: "Адрес", placeholder: "г. Москва, ул. Примерная, 1", wide: true },
  { key: "return_address", label: "Адрес возврата", placeholder: "г. Москва, ул. Примерная, 1", wide: true },
  { key: "age_restriction", label: "Ограничение по возрасту", placeholder: "18+" },
  { key: "deposit_return", label: "Условия возврата залога", wide: true },
  { key: "photo_consent", label: "Согласие на фото", wide: true },
];

function GeneralTab() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<CompanyProfile | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["settings", "company"],
    queryFn: async () => {
      const { data } = await api.get<CompanyProfile>("/settings/company");
      return data;
    },
  });

  useEffect(() => {
    if (data) setForm(data);
  }, [data]);

  const save = useMutation({
    mutationFn: async (payload: CompanyProfile) => {
      await api.patch("/settings/company", payload);
    },
    onSuccess: () => {
      toast({ title: "Реквизиты сохранены" });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (error: { response?: { data?: { detail?: string } } }) => {
      toast({ title: "Ошибка", description: error.response?.data?.detail || "Не удалось сохранить реквизиты" });
    },
  });

  if (isLoading || !form) {
    return <p className="text-sm text-muted-foreground">Загрузка реквизитов…</p>;
  }

  const set = (key: keyof CompanyProfile, value: string) =>
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold">Реквизиты арендодателя</h2>
        <p className="text-sm text-muted-foreground">
          Эти данные подставляются в договор аренды. Заполните их, чтобы в документах не было
          прочерков.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {COMPANY_FIELDS.map((field) => (
          <div key={field.key} className={cn("space-y-1.5", field.wide && "sm:col-span-2")}>
            <label className="text-sm font-medium" htmlFor={field.key}>
              {field.label}
            </label>
            <input
              id={field.key}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              value={(form[field.key] as string) || ""}
              placeholder={field.placeholder}
              onChange={(e) => set(field.key, e.target.value)}
            />
          </div>
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(form);
        }}
      >
        <button
          type="submit"
          disabled={save.isPending}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          <Save className="h-4 w-4" />
          {save.isPending ? "Сохраняем…" : "Сохранить реквизиты"}
        </button>
      </form>
    </div>
  );
}

/* ---------- Аккаунт ---------- */

function AccountTab() {
  const queryClient = useQueryClient();
  const [profile, setProfile] = useState({ full_name: "", phone: "", telegram_chat_id: "" });
  const [passwords, setPasswords] = useState({ current_password: "", new_password: "", repeat: "" });

  const { data, isLoading } = useQuery({
    queryKey: ["settings", "account"],
    queryFn: async () => {
      const { data } = await api.get("/settings/account");
      return data as {
        full_name: string;
        phone: string | null;
        email: string;
        role: string;
        telegram_chat_id: string | null;
      };
    },
  });

  useEffect(() => {
    if (data) {
      setProfile({
        full_name: data.full_name || "",
        phone: data.phone || "",
        telegram_chat_id: data.telegram_chat_id || "",
      });
    }
  }, [data]);

  const saveProfile = useMutation({
    mutationFn: async (payload: typeof profile) => {
      await api.patch("/settings/account", payload);
    },
    onSuccess: () => {
      toast({ title: "Профиль обновлён" });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (error: { response?: { data?: { detail?: string } } }) => {
      toast({ title: "Ошибка", description: error.response?.data?.detail || "Не удалось сохранить профиль" });
    },
  });

  const changePassword = useMutation({
    mutationFn: async (payload: { current_password: string; new_password: string }) => {
      await api.post("/settings/account/password", payload);
    },
    onSuccess: () => {
      toast({ title: "Пароль изменён" });
      setPasswords({ current_password: "", new_password: "", repeat: "" });
    },
    onError: (error: { response?: { data?: { detail?: string } } }) => {
      toast({ title: "Ошибка", description: error.response?.data?.detail || "Не удалось изменить пароль" });
    },
  });

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Загрузка профиля…</p>;
  }

  const passwordHint = () => {
    if (passwords.repeat && passwords.new_password !== passwords.repeat) {
      return "Пароли не совпадают";
    }
    return null;
  };
  const hint = passwordHint();

  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <div>
          <h2 className="text-base font-semibold">Профиль</h2>
          <p className="text-sm text-muted-foreground">
            Логин — {data?.email}. Роль и email меняет администратор.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="full_name">
              ФИО
            </label>
            <input
              id="full_name"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              value={profile.full_name}
              onChange={(e) => setProfile((p) => ({ ...p, full_name: e.target.value }))}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="phone">
              Телефон
            </label>
            <input
              id="phone"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              value={profile.phone}
              placeholder="+7 900 000-00-00"
              onChange={(e) => setProfile((p) => ({ ...p, phone: e.target.value }))}
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <label className="text-sm font-medium" htmlFor="telegram_chat_id">
              Telegram chat_id
            </label>
            <input
              id="telegram_chat_id"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              value={profile.telegram_chat_id}
              placeholder="123456789"
              onChange={(e) => setProfile((p) => ({ ...p, telegram_chat_id: e.target.value }))}
            />
          </div>
        </div>

        <button
          onClick={() => saveProfile.mutate(profile)}
          disabled={saveProfile.isPending}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          <Save className="h-4 w-4" />
          {saveProfile.isPending ? "Сохраняем…" : "Сохранить профиль"}
        </button>
      </section>

      <section className="space-y-4 border-t pt-6">
        <div>
          <h2 className="text-base font-semibold">Смена пароля</h2>
          <p className="text-sm text-muted-foreground">Новый пароль — не короче 8 символов.</p>
        </div>

        <div className="grid max-w-md gap-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="current_password">
              Текущий пароль
            </label>
            <input
              id="current_password"
              type="password"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              value={passwords.current_password}
              onChange={(e) =>
                setPasswords((p) => ({ ...p, current_password: e.target.value }))
              }
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="new_password">
              Новый пароль
            </label>
            <input
              id="new_password"
              type="password"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              value={passwords.new_password}
              onChange={(e) => setPasswords((p) => ({ ...p, new_password: e.target.value }))}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="repeat">
              Повторите новый пароль
            </label>
            <input
              id="repeat"
              type="password"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              value={passwords.repeat}
              onChange={(e) => setPasswords((p) => ({ ...p, repeat: e.target.value }))}
            />
            {hint && <p className="text-xs text-destructive">{hint}</p>}
          </div>
        </div>

        <button
          onClick={() => {
            if (hint) return;
            changePassword.mutate({
              current_password: passwords.current_password,
              new_password: passwords.new_password,
            });
          }}
          disabled={
            changePassword.isPending ||
            !passwords.current_password ||
            !passwords.new_password ||
            Boolean(hint)
          }
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          <KeyRound className="h-4 w-4" />
          {changePassword.isPending ? "Меняем…" : "Изменить пароль"}
        </button>
      </section>
    </div>
  );
}

/* ---------- Интеграции ---------- */

interface IntegrationSummary {
  id: string;
  name: string;
  title: string;
  is_enabled: boolean;
  is_configured: boolean;
  secret_fields: string[];
}

interface EmailSettingsResponse {
  is_enabled: boolean;
  config: {
    provider: "smtp" | "resend";
    host: string | null;
    port: number;
    username: string | null;
    from_email: string | null;
    from_name: string | null;
    use_tls: boolean;
  };
  password_set: boolean;
  api_key_set: boolean;
  from_env: boolean;
}

/** Форма редактирования: пустые значения — обычные строки, не null. */
interface EmailForm {
  provider: "smtp" | "resend";
  host: string;
  port: number;
  username: string;
  from_email: string;
  from_name: string;
  use_tls: boolean;
}

function EmailIntegration() {
  const queryClient = useQueryClient();
  const [enabled, setEnabled] = useState(false);
  const [form, setForm] = useState<EmailForm>({
    provider: "smtp",
    host: "",
    port: 587,
    username: "",
    from_email: "",
    from_name: "",
    use_tls: true,
  });
  const [password, setPassword] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [testTo, setTestTo] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["settings", "integrations", "email"],
    queryFn: async () => {
      const { data } = await api.get<EmailSettingsResponse>("/settings/integrations/email");
      return data;
    },
  });

  useEffect(() => {
    if (!data) return;
    setEnabled(data.is_enabled);
    setForm({
      provider: data.config.provider,
      host: data.config.host || "",
      port: data.config.port || 587,
      username: data.config.username || "",
      from_email: data.config.from_email || "",
      from_name: data.config.from_name || "",
      use_tls: data.config.use_tls,
    });
  }, [data]);

  const save = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = {
        is_enabled: enabled,
        config: { ...form, port: Number(form.port) || 587 },
      };
      // Пустая строка означает «оставить прежний секрет»
      if (password) payload.password = password;
      if (apiKey) payload.api_key = apiKey;
      const { data } = await api.patch<EmailSettingsResponse>(
        "/settings/integrations/email",
        payload
      );
      return data;
    },
    onSuccess: () => {
      setPassword("");
      setApiKey("");
      toast({ title: "Настройки почты сохранены" });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (error: { response?: { data?: { detail?: string } } }) => {
      toast({ title: "Ошибка", description: error.response?.data?.detail || "Не удалось сохранить настройки почты" });
    },
  });

  const test = useMutation({
    mutationFn: async (to: string) => {
      const { data } = await api.post<{ detail: string }>("/settings/integrations/email/test", {
        to_email: to,
      });
      return data;
    },
    onSuccess: (data) => toast({ title: data?.detail || "Письмо отправлено" }),
    onError: (error: { response?: { data?: { detail?: string } } }) => {
      toast({ title: "Ошибка", description: error.response?.data?.detail || "Не удалось отправить тестовое письмо" });
    },
  });

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Загрузка настроек почты…</p>;
  }

  const isResend = form.provider === "resend";
  const set = (patch: Partial<EmailForm>) => setForm((prev) => ({ ...prev, ...patch }));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <Mail className="h-4 w-4" />
            Электронная почта
          </h3>
          <p className="text-sm text-muted-foreground">
            Отправка писем клиентам: подтверждения, договоры, уведомления.
          </p>
        </div>
        <label className="inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="h-4 w-4"
          />
          <Power className={cn("h-4 w-4", enabled ? "text-green-600" : "text-muted-foreground")} />
          {enabled ? "Включена" : "Выключена"}
        </label>
      </div>

      {data?.from_env && (
        <p className="rounded-md border border-dashed bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          Сейчас письма отправляются по настройкам из .env. Сохраните здесь свои данные — они
          станут приоритетными.
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label className="text-sm font-medium" htmlFor="provider">
            Провайдер
          </label>
          <select
            id="provider"
            className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            value={form.provider}
            onChange={(e) => set({ provider: e.target.value as "smtp" | "resend" })}
          >
            <option value="smtp">SMTP</option>
            <option value="resend">Resend</option>
          </select>
        </div>

        <div className="space-y-1.5">
          <label className="text-sm font-medium" htmlFor="from_email">
            Email отправителя
          </label>
          <input
            id="from_email"
            className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            value={form.from_email}
            placeholder="noreply@example.com"
            onChange={(e) => set({ from_email: e.target.value })}
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-sm font-medium" htmlFor="from_name">
            Имя отправителя
          </label>
          <input
            id="from_name"
            className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            value={form.from_name}
            placeholder="ВЖУХ и поехали"
            onChange={(e) => set({ from_name: e.target.value })}
          />
        </div>

        {isResend ? (
          <div className="space-y-1.5 sm:col-span-2">
            <label className="text-sm font-medium" htmlFor="api_key">
              API-ключ Resend {data?.api_key_set && "(сохранён)"}
            </label>
            <input
              id="api_key"
              type="password"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              value={apiKey}
              placeholder={data?.api_key_set ? "•••••••• — оставьте пустым, чтобы не менять" : "re_..."}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>
        ) : (
          <>
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="host">
                SMTP-сервер
              </label>
              <input
                id="host"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                value={form.host}
                placeholder="smtp.yandex.ru"
                onChange={(e) => set({ host: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="port">
                Порт
              </label>
              <input
                id="port"
                type="number"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                value={form.port}
                onChange={(e) => set({ port: Number(e.target.value) })}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="username">
                Логин
              </label>
              <input
                id="username"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                value={form.username}
                onChange={(e) => set({ username: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="password">
                Пароль {data?.password_set && "(сохранён)"}
              </label>
              <input
                id="password"
                type="password"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                value={password}
                placeholder={data?.password_set ? "•••••••• — оставьте пустым, чтобы не менять" : ""}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <label className="inline-flex items-center gap-2 text-sm sm:col-span-2">
              <input
                type="checkbox"
                checked={form.use_tls}
                onChange={(e) => set({ use_tls: e.target.checked })}
                className="h-4 w-4"
              />
              Использовать STARTTLS (для порта 465 — SSL, галочку снимите)
            </label>
          </>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => save.mutate()}
          disabled={save.isPending}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          <Save className="h-4 w-4" />
          {save.isPending ? "Сохраняем…" : "Сохранить"}
        </button>
      </div>

      <div className="space-y-2 rounded-md border bg-muted/20 p-3">
        <p className="text-sm font-medium">Проверить отправку</p>
        <p className="text-xs text-muted-foreground">
          Сначала сохраните настройки, затем отправьте письмо на свой адрес.
        </p>
        <div className="flex flex-wrap gap-2">
          <input
            className="min-w-0 flex-1 rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            value={testTo}
            placeholder="ваш@email.ru"
            onChange={(e) => setTestTo(e.target.value)}
          />
          <button
            onClick={() => test.mutate(testTo)}
            disabled={test.isPending || !testTo}
            className="inline-flex items-center gap-2 rounded-md border bg-background px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            <Inbox className="h-4 w-4" />
            {test.isPending ? "Отправляем…" : "Отправить тест"}
          </button>
        </div>
      </div>
    </div>
  );
}

const PLANNED: Record<string, string> = {
  telegram: "Уведомления о новых заявках в чат команды",
  avito: "Публикация байков и приём откликов",
  vk: "Рассылки и обработка сообщений сообщества",
  widget: "Форма бронирования для сайта",
};

function IntegrationsTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["settings", "integrations"],
    queryFn: async () => {
      const { data } = await api.get<IntegrationSummary[]>("/settings/integrations");
      return data;
    },
  });

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Загрузка интеграций…</p>;
  }

  const others = (data || []).filter((item) => item.name !== "email");

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold">Интеграции</h2>
        <p className="text-sm text-muted-foreground">
          Подключённые сервисы, через которые CRM общается с клиентами и командой.
        </p>
      </div>

      <div className="rounded-lg border p-4">
        <EmailIntegration />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {others.map((item) => (
          <div key={item.id} className="rounded-lg border border-dashed p-4">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-medium">{item.title}</p>
              <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                Скоро
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {PLANNED[item.name] || "В разработке"}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------- Страница ---------- */

export default function SettingsPage() {
  const [tab, setTab] = useState<TabKey>("general");

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-bold">
          <CheckCircle2 className="h-5 w-5" />
          Настройки
        </h1>
        <p className="text-sm text-muted-foreground">
          Реквизиты компании, данные аккаунта и подключённые сервисы.
        </p>
      </div>

      <div className="flex flex-wrap gap-1 rounded-lg border p-1">
        {TABS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.key}
              onClick={() => setTab(item.key)}
              className={cn(
                "inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                tab === item.key
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted"
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </button>
          );
        })}
      </div>

      <div className="rounded-lg border p-5">
        {tab === "general" && <GeneralTab />}
        {tab === "account" && <AccountTab />}
        {tab === "integrations" && <IntegrationsTab />}
      </div>
    </div>
  );
}