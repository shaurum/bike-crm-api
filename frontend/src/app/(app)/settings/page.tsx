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
  RefreshCw,
  Save,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "@/hooks/use-toast";

import { api, systemApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { apiErrorMessage, cn } from "@/lib/utils";

import UsersTab from "./users-tab";

type TabKey = "general" | "account" | "users" | "integrations" | "update";

const TABS: {
  key: TabKey;
  label: string;
  icon: typeof Building2;
  adminOnly?: boolean;
}[] = [
  { key: "general", label: "Основное", icon: Building2 },
  { key: "account", label: "Аккаунт", icon: UserRound },
  { key: "users", label: "Пользователи", icon: ShieldCheck, adminOnly: true },
  { key: "integrations", label: "Интеграции", icon: Plug },
  { key: "update", label: "Обновление", icon: RefreshCw },
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

const EMPTY_COMPANY: CompanyProfile = {
  name: "",
  ogrnip: null,
  inn: null,
  phone: null,
  email: null,
  address: null,
  return_address: null,
  age_restriction: null,
  deposit_return: null,
  photo_consent: null,
};

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

  const { data, isLoading, error } = useQuery({
    queryKey: ["settings", "company"],
    queryFn: async () => {
      const { data } = await api.get<CompanyProfile>("/settings/company");
      return data;
    },
    // 404 значит, что реквизитов ещё нет: не повторяем запрос, а показываем пустую форму
    retry: (count, err) =>
      (err as { response?: { status?: number } })?.response?.status !== 404 && count < 2,
  });
  const notFound = (error as { response?: { status?: number } } | null)?.response?.status === 404;

  useEffect(() => {
    if (data) setForm(data);
    else if (notFound) setForm(EMPTY_COMPANY);
  }, [data, notFound]);

  const save = useMutation({
    mutationFn: async (payload: CompanyProfile) => {
      await api.patch("/settings/company", payload);
    },
    onSuccess: () => {
      toast({ title: "Реквизиты сохранены" });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (error: { response?: { data?: { detail?: string } } }) => {
      toast({ title: "Ошибка", description: apiErrorMessage(error, "Не удалось сохранить реквизиты") });
    },
  });

  if (error && !notFound) {
    return (
      <p className="text-sm text-red-600">
        Не удалось загрузить реквизиты. Проверьте соединение и обновите страницу.
      </p>
    );
  }

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
      toast({ title: "Ошибка", description: apiErrorMessage(error, "Не удалось сохранить профиль") });
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
      toast({ title: "Ошибка", description: apiErrorMessage(error, "Не удалось изменить пароль") });
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
    imap_host: string | null;
    imap_port: number;
    imap_username: string | null;
    imap_use_ssl: boolean;
    imap_folder: string;
  };
  password_set: boolean;
  api_key_set: boolean;
  imap_password_set: boolean;
  from_env: boolean;
  imap_ready: boolean;
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
  imap_host: string;
  imap_port: number;
  imap_username: string;
  imap_use_ssl: boolean;
  imap_folder: string;
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
    imap_host: "",
    imap_port: 993,
    imap_username: "",
    imap_use_ssl: true,
    imap_folder: "INBOX",
  });
  const [password, setPassword] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [imapPassword, setImapPassword] = useState("");
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
      imap_host: data.config.imap_host || "",
      imap_port: data.config.imap_port || 993,
      imap_username: data.config.imap_username || "",
      imap_use_ssl: data.config.imap_use_ssl,
      imap_folder: data.config.imap_folder || "INBOX",
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
      if (imapPassword) payload.imap_password = imapPassword;
      const { data } = await api.patch<EmailSettingsResponse>(
        "/settings/integrations/email",
        payload
      );
      return data;
    },
    onSuccess: () => {
      setPassword("");
      setApiKey("");
      setImapPassword("");
      toast({ title: "Настройки почты сохранены" });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (error: { response?: { data?: { detail?: string } } }) => {
      toast({ title: "Ошибка", description: apiErrorMessage(error, "Не удалось сохранить настройки почты") });
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
      toast({ title: "Ошибка", description: apiErrorMessage(error, "Не удалось отправить тестовое письмо") });
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

      <div className="space-y-3 border-t pt-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-medium">Приём входящих писем (IMAP)</p>
          <span
            className={
              data?.imap_ready
                ? "inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-[11px] text-green-800"
                : "inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground"
            }
          >
            {data?.imap_ready ? "Приём настроен" : "Приём не настроен"}
          </span>
        </div>
        <p className="text-xs text-muted-foreground">
          Без IMAP входящие письма приходят только через вебхук провайдера.
          Заполните сервер, логин и пароль — письма будут забираться сами
          раз в минуту.
        </p>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="imap_host">
              IMAP-сервер
            </label>
            <input
              id="imap_host"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              value={form.imap_host}
              placeholder="imap.yandex.com"
              onChange={(e) => set({ imap_host: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="imap_port">
              Порт IMAP
            </label>
            <input
              id="imap_port"
              type="number"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              value={form.imap_port}
              onChange={(e) => set({ imap_port: Number(e.target.value) })}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="imap_username">
              Логин IMAP
            </label>
            <input
              id="imap_username"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              value={form.imap_username}
              placeholder="mail@example.com"
              onChange={(e) => set({ imap_username: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="imap_password">
              Пароль IMAP {data?.imap_password_set && "(сохранён)"}
            </label>
            <input
              id="imap_password"
              type="password"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              value={imapPassword}
              placeholder={
                data?.imap_password_set
                  ? "\u2022\u2022\u2022\u2022\u2022\u2022 \u2014 оставьте пустым, чтобы не менять"
                  : ""
              }
              onChange={(e) => setImapPassword(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="imap_folder">
              Папка
            </label>
            <input
              id="imap_folder"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              value={form.imap_folder}
              onChange={(e) => set({ imap_folder: e.target.value })}
            />
          </div>
          <label className="inline-flex items-center gap-2 self-end pb-2 text-sm">
            <input
              type="checkbox"
              checked={form.imap_use_ssl}
              onChange={(e) => set({ imap_use_ssl: e.target.checked })}
              className="h-4 w-4"
            />
            SSL (обычно на порту 993)
          </label>
        </div>
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

interface AvitoSettingsResponse {
  is_enabled: boolean;
  config: { redirect_uri: string | null; scopes: string };
  client_id_set: boolean;
  client_secret_set: boolean;
  connected: boolean;
  user_id: number | null;
  account_name: string | null;
  account_phone: string | null;
  token_expires_at: string | null;
  connected_at: string | null;
  ready_to_connect: boolean;
}

function AvitoIntegration() {
  const queryClient = useQueryClient();
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [redirectUri, setRedirectUri] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["settings", "integrations", "avito"],
    queryFn: async () => {
      const { data } = await api.get<AvitoSettingsResponse>(
        "/settings/integrations/avito"
      );
      return data;
    },
  });

  useEffect(() => {
    if (!data) return;
    setClientId("");
    setClientSecret("");
    setRedirectUri(data.config.redirect_uri || "");
  }, [data]);

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["settings"] });

  const onError = (error: { response?: { data?: { detail?: string } } }) => {
    toast({
      title: "Ошибка",
      description: apiErrorMessage(error, "Не удалось выполнить действие"),
    });
  };

  const save = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = {
        config: {
          redirect_uri: redirectUri || null,
          scopes: data?.config.scopes,
        },
      };
      if (clientId) payload.client_id = clientId;
      if (clientSecret) payload.client_secret = clientSecret;
      const { data: saved } = await api.patch<AvitoSettingsResponse>(
        "/settings/integrations/avito",
        payload
      );
      return saved;
    },
    onSuccess: () => {
      setClientId("");
      setClientSecret("");
      toast({ title: "Реквизиты приложения Авито сохранены" });
      invalidate();
    },
    onError,
  });

  const connect = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ url: string }>(
        "/settings/integrations/avito/connect-url"
      );
      return data;
    },
    onSuccess: (payload) => {
      window.location.href = payload.url;
    },
    onError,
  });

  const disconnect = useMutation({
    mutationFn: async () => {
      await api.post("/settings/integrations/avito/disconnect");
    },
    onSuccess: () => {
      toast({ title: "Доступ к Авито отозван" });
      invalidate();
    },
    onError,
  });

  if (isLoading || !data) {
    return <p className="text-sm text-muted-foreground">Загрузка настроек Авито…</p>;
  }

  const accountLabel =
    data.account_name || data.account_phone || (data.user_id ? `id ${data.user_id}` : "");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium">Авито</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Переписка с покупателями из объявлений приходит в раздел «Сообщения»,
            отвечать можно оттуда же.
          </p>
        </div>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-xs",
            data.connected
              ? "bg-green-100 text-green-800"
              : "bg-amber-50 text-amber-700"
          )}
        >
          {data.connected ? "Подключено" : "Не подключено"}
        </span>
      </div>

      {data.connected && (
        <div className="rounded-md border border-green-200 bg-green-50 p-3 text-xs text-green-900">
          Авторизован аккаунт{accountLabel ? ` «${accountLabel}»` : ""}.
          Входящие сообщения подхватываются автоматически, ответы уходят из чата.
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block space-y-1">
          <span className="text-xs text-muted-foreground">client_id</span>
          <input
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            placeholder={data.client_id_set ? "сохранено" : "из кабинета разработчика"}
            autoComplete="off"
            className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-xs text-muted-foreground">client_secret</span>
          <input
            type="password"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            placeholder={data.client_secret_set ? "сохранён" : "из кабинета разработчика"}
            autoComplete="off"
            className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
        </label>
        <label className="block space-y-1 sm:col-span-2">
          <span className="text-xs text-muted-foreground">
            Redirect URI — должен совпадать с указанным при регистрации приложения
          </span>
          <input
            value={redirectUri}
            onChange={(e) => setRedirectUri(e.target.value)}
            placeholder="https://ваш-домен/settings/avito/callback"
            autoComplete="off"
            className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
          <span className="block text-[11px] text-amber-600">
            Авито принимает только адреса по https — локальный http://localhost не подойдёт.
          </span>
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => save.mutate()}
          disabled={save.isPending}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground"
        >
          <Save className="h-4 w-4" />
          Сохранить
        </button>
        <button
          onClick={() => connect.mutate()}
          disabled={!data.ready_to_connect || connect.isPending}
          title={
            data.ready_to_connect
              ? "Открыть страницу подтверждения в Авито"
              : "Сначала сохраните client_id, client_secret и redirect_uri"
          }
          className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm font-medium transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Plug className="h-4 w-4" />
          {data.connected ? "Переподключить" : "Подключить Авито"}
        </button>
        {data.connected && (
          <button
            onClick={() => disconnect.mutate()}
            disabled={disconnect.isPending}
            className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-50 disabled:opacity-50"
          >
            <Power className="h-4 w-4" />
            Отключить
          </button>
        )}
      </div>

      <p className="text-[11px] text-muted-foreground">
        Реквизиты выдаются в кабинете разработчика Авито после регистрации приложения
        и письма с ключами. Для мессенджера нужен тариф «Расширенный» или «Максимальный».
      </p>
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

  const others = (data || []).filter(
    (item) => item.name !== "email" && item.name !== "avito"
  );

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

      <div className="rounded-lg border p-4">
        <AvitoIntegration />
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

/* ---------- Обновление ---------- */

function UpdateTab() {
  const isAdmin = useAuthStore((state) => state.user?.role === "admin");

  const { data, refetch, isFetching } = useQuery({
    queryKey: ["system", "version"],
    queryFn: async () => (await systemApi.version()).data,
    refetchInterval: (query) => (query.state.data?.updating ? 3000 : 60000),
  });

  const check = useMutation({
    mutationFn: async () => (await systemApi.checkUpdate()).data,
    onSuccess: (res) => {
      toast({ title: res.ok ? "Проверка запущена" : "Недоступно", description: res.detail });
      if (res.ok) {
        setTimeout(() => refetch(), 2500);
      }
    },
    onError: (error: { response?: { data?: { detail?: string } } }) =>
      toast({
        title: "Ошибка",
        description: apiErrorMessage(error, "Не удалось запросить обновление"),
      }),
  });

  const setMode = useMutation({
    mutationFn: async (mode: "auto" | "manual") => (await systemApi.setUpdateMode(mode)).data,
    onSuccess: (res) => {
      toast({ title: "Режим обновления изменён", description: res.mode === "auto" ? "Новые версии ставятся автоматически" : "Обновления только по кнопке" });
      refetch();
    },
    onError: (error: { response?: { data?: { detail?: string } } }) =>
      toast({
        title: "Ошибка",
        description: apiErrorMessage(error, "Не удалось изменить режим"),
      }),
  });

  if (!data) {
    return <p className="text-sm text-muted-foreground">Загрузка версии…</p>;
  }

  const mode = data.mode === "manual" ? "manual" : "auto";
  const versionLabel = data.current_tag || (data.current_sha ? `#${data.current_sha}` : "неизвестно");
  const remoteLabel = data.current_tag && data.remote_sha && data.current_tag !== data.remote_sha
    ? data.remote_sha
    : data.remote_sha;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold">Обновление CRM</h2>
        <p className="text-sm text-muted-foreground">
          Проверяет GitHub-релизы каждые 5 минут. Каждая версия — это тег
          <span className="font-mono"> v*</span> с zip-архивом; откат — установить предыдущий релиз.
        </p>
      </div>

      {isAdmin && (
        <div className="flex items-center justify-between gap-3 rounded-md border p-3">
          <div>
            <p className="text-sm font-medium">Режим установки</p>
            <p className="text-xs text-muted-foreground">
              {mode === "auto"
                ? "Новые версии устанавливаются сразу после проверки"
                : "Обновление ставится только по кнопке «Проверить и установить»"}
            </p>
          </div>
          <div className="flex shrink-0 gap-1 rounded-md border p-1">
            <button
              onClick={() => setMode.mutate("auto")}
              disabled={setMode.isPending || data.updating}
              className={cn(
                "rounded px-3 py-1 text-sm font-medium transition-colors disabled:opacity-50",
                mode === "auto" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
              )}
            >
              Авто
            </button>
            <button
              onClick={() => setMode.mutate("manual")}
              disabled={setMode.isPending || data.updating}
              className={cn(
                "rounded px-3 py-1 text-sm font-medium transition-colors disabled:opacity-50",
                mode === "manual" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
              )}
            >
              Вручную
            </button>
          </div>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-md border p-3">
          <p className="text-xs text-muted-foreground">Текущая версия</p>
          <p className="mt-1 font-mono text-sm">{versionLabel}</p>
          {data.current_date && (
            <p className="text-xs text-muted-foreground">
              {new Date(data.current_date).toLocaleString("ru-RU")}
            </p>
          )}
        </div>
        <div className="rounded-md border p-3">
          <p className="text-xs text-muted-foreground">Последняя проверка</p>
          <p className="mt-1 text-sm">
            {data.last_check
              ? new Date(data.last_check).toLocaleString("ru-RU")
              : "ещё не выполнялась"}
          </p>
          <p className="text-xs text-muted-foreground">
            {data.auto_update ? "Автообновление: включено (по расписанию)" : "Автообновление не настроено"}
          </p>
        </div>
      </div>

      {data.updating && (
        <div className="flex items-center gap-2 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-800">
          <RefreshCw className="h-4 w-4 animate-spin" aria-hidden />
          Обновление устанавливается — CRM перезапустится через минуту
        </div>
      )}

      {!data.updating && data.update_available && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Доступна новая версия {remoteLabel ? `${remoteLabel}` : ""}
          {mode === "auto"
            ? " — установится автоматически в течение минуты"
            : " — нажмите «Проверить и установить»"}
        </div>
      )}

      {!data.updating && !data.update_available && (
        <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800">
          Установлена последняя версия
        </div>
      )}

      {isAdmin && (
        <button
          onClick={() => check.mutate()}
          disabled={check.isPending || data.updating || isFetching}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          <RefreshCw className={cn("h-4 w-4", check.isPending && "animate-spin")} />
          {check.isPending
            ? "Проверяем…"
            : mode === "manual"
              ? "Проверить и установить"
              : "Проверить обновления сейчас"}
        </button>
      )}

      {data.note && (
        <p className="text-xs text-muted-foreground">Статус: {data.note}</p>
      )}
    </div>
  );
}

/* ---------- Страница ---------- */

export default function SettingsPage() {
  const [tab, setTab] = useState<TabKey>("general");
  const isAdmin = useAuthStore((state) => state.user?.role === "admin");

  const tabs = TABS.filter((item) => !item.adminOnly || isAdmin);

  useEffect(() => {
    const wanted = new URLSearchParams(window.location.search).get("tab");
    if (
      wanted === "general" ||
      wanted === "account" ||
      wanted === "users" ||
      wanted === "integrations" ||
      wanted === "update"
    ) {
      setTab(wanted);
    }
  }, []);

  // Невидимую вкладку (не-admin заходил по прямой ссылке) не показываем
  const activeTab = tabs.some((item) => item.key === tab) ? tab : "general";

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-bold">
          <CheckCircle2 className="h-5 w-5" />
          Настройки
        </h1>
        <p className="text-sm text-muted-foreground">
          Реквизиты компании, данные аккаунта, сотрудники и подключённые сервисы.
        </p>
      </div>

      <div className="flex flex-wrap gap-1 rounded-lg border p-1">
        {tabs.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.key}
              onClick={() => setTab(item.key)}
              className={cn(
                "inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                activeTab === item.key
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
        {activeTab === "general" && <GeneralTab />}
        {activeTab === "account" && <AccountTab />}
        {activeTab === "users" && <UsersTab />}
        {activeTab === "integrations" && <IntegrationsTab />}
        {activeTab === "update" && <UpdateTab />}
      </div>
    </div>
  );
}