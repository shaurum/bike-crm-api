"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  ArrowLeft,
  CheckCheck,
  Lock,
  Paperclip,
  Plus,
  RotateCw,
  Search,
  Send,
  Trash2,
  Unlock,
  User,
  X,
} from "lucide-react";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "@/hooks/use-toast";

import { ChannelIcon } from "@/components/channel-icon";
import { CannedRepliesMenu } from "@/components/canned-replies";
import { API_URL, api } from "@/lib/api";
import { apiErrorMessage, cn } from "@/lib/utils";

interface ConversationItem {
  id: string;
  status: string;
  is_archived: boolean;
  last_message_at: string | null;
  unread_count: number;
  customer_id: string;
  customer_name: string;
  lead_id: string | null;
  deal_state: "active" | "deal_closed" | "none";
  preview: string | null;
  channel: string | null;
  awaiting_reply: boolean;
  contacts: string[];
}

interface ContactPoint {
  id: string;
  channel: string;
  value: string;
  label: string | null;
  is_primary: boolean;
  is_verified: boolean;
}

interface MessageAttachment {
  url: string;
  name?: string | null;
  content_type?: string | null;
}

interface MessageItem {
  id: string;
  channel: string;
  direction: string;
  content: string;
  is_read: boolean;
  /** false — канал не принял сообщение (например, Telegram не подключён). */
  delivered?: boolean | null;
  author_name: string | null;
  subject: string | null;
  attachments?: MessageAttachment[];
  created_at: string;
}

interface ConversationDetail {
  id: string;
  status: string;
  is_archived: boolean;
  unread_count: number;
  customer_id: string;
  customer_name: string;
  customer_phone: string | null;
  customer_email: string | null;
  lead_id: string | null;
  deal_state: "active" | "deal_closed" | "none";
  contacts: ContactPoint[];
  messages: MessageItem[];
  channels: string[];
}

const CHANNEL_LABELS: Record<string, string> = {
  email: "Почта",
  telegram: "Telegram",
  vk: "ВКонтакте",
  avito: "Авито",
  whatsapp: "WhatsApp",
  phone: "Телефон",
  internal: "Внутренняя заметка",
};

const DEAL_LABELS: Record<string, string> = {
  active: "В аренде",
  deal_closed: "Сделки нет",
  none: "Нет сделки",
};

/** Каналы, в которые реально можно отправить (СМС и WhatsApp не подключены). */
const SENDABLE_CHANNELS = new Set(["email", "telegram", "vk", "avito"]);

function formatTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function AwaitingBadge() {
  return (
    <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-orange-500 px-2 py-0.5 text-[11px] font-semibold text-white">
      Ждёт ответа
    </span>
  );
}

function DealBadge({ state }: { state: string }) {
  if (state === "active") {
    return (
      <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-[11px] font-medium text-green-800">
        {DEAL_LABELS.active}
      </span>
    );
  }
  if (state === "deal_closed") {
    return (
      <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800">
        {DEAL_LABELS.deal_closed}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
      {DEAL_LABELS.none}
    </span>
  );
}

/* ---------- Список диалогов ---------- */

function ConversationList({
  search,
  filter,
  archived,
  selectedId,
  onSelect,
  onMarkRead,
}: {
  search: string;
  filter: string;
  archived: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onMarkRead: (id: string) => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["conversations", search, filter, archived],
    queryFn: async () => {
      const { data } = await api.get<ConversationItem[]>("/conversations", {
        params: {
          search: search || undefined,
          status_filter: filter,
          archived: archived ? true : undefined,
        },
      });
      return data;
    },
    refetchInterval: 15000,
  });

  if (isLoading) {
    return <p className="p-4 text-sm text-muted-foreground">Загрузка…</p>;
  }
  if (!data || data.length === 0) {
    return (
      <p className="p-6 text-center text-sm text-muted-foreground">
        {archived
          ? "Архив пуст"
          : search || filter !== "all"
            ? "Ничего не найдено"
            : "Сообщений пока нет"}
      </p>
    );
  }

  return (
    <div className="divide-y">
      {data.map((item) => (
        <div
          key={item.id}
          role="button"
          tabIndex={0}
          onClick={() => onSelect(item.id)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSelect(item.id);
          }}
          className={cn(
            "block w-full cursor-pointer border-l-2 px-4 py-3 text-left transition-colors hover:bg-muted/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            selectedId === item.id
              ? "border-primary bg-muted"
              : item.unread_count > 0
                ? "border-primary bg-primary/5"
                : "border-transparent"
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <span
              className={cn(
                "truncate text-sm",
                item.unread_count > 0 ? "font-semibold" : "font-medium"
              )}
            >
              {item.customer_name}
            </span>
            <span className="shrink-0 text-[11px] text-muted-foreground">
              {formatTime(item.last_message_at)}
            </span>
          </div>

          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {item.awaiting_reply && <AwaitingBadge />}
            <DealBadge state={item.deal_state} />
            {item.channel && (
              <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                <ChannelIcon channel={item.channel} className="h-3.5 w-3.5" />
                {CHANNEL_LABELS[item.channel] || item.channel}
              </span>
            )}
          </div>

          <div className="mt-1 flex items-start justify-between gap-2">
            <p
              className={cn(
                "line-clamp-2 text-xs",
                item.unread_count > 0
                  ? "font-medium text-foreground"
                  : "text-muted-foreground"
              )}
            >
              {item.preview || "Нет сообщений"}
            </p>
            {item.unread_count > 0 && (
              <div className="mt-0.5 flex shrink-0 items-center gap-1">
                <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[11px] font-semibold text-primary-foreground ring-2 ring-background">
                  {item.unread_count}
                </span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onMarkRead(item.id);
                  }}
                  title="Отметить прочитанным"
                  className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <CheckCheck className="h-3.5 w-3.5" />
                </button>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ---------- Контакты клиента ---------- */

function ContactsPanel({
  customerId,
  contacts,
}: {
  customerId: string;
  contacts: ContactPoint[];
}) {
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [channel, setChannel] = useState("email");
  const [value, setValue] = useState("");
  const [label, setLabel] = useState("");

  const add = useMutation({
    mutationFn: async () => {
      await api.post(`/conversations/contacts/${customerId}`, {
        channel,
        value,
        label: label || null,
      });
    },
    onSuccess: () => {
      toast({ title: "Контакт добавлен" });
      setAdding(false);
      setValue("");
      setLabel("");
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      queryClient.invalidateQueries({ queryKey: ["conversation"] });
    },
    onError: (error: { response?: { data?: { detail?: unknown } } }) => {
      toast({
        title: "Не удалось добавить",
        description: apiErrorMessage(error, "Ошибка сохранения"),
      });
    },
  });

  const remove = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/conversations/contacts/${id}`);
    },
    onSuccess: () => {
      toast({ title: "Контакт удалён" });
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      queryClient.invalidateQueries({ queryKey: ["conversation"] });
    },
    onError: (error: { response?: { data?: { detail?: unknown } } }) => {
      toast({
        title: "Не удалось удалить",
        description: apiErrorMessage(error, "Ошибка удаления"),
      });
    },
  });

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase text-muted-foreground">
          Способы связи
        </p>
        <button
          onClick={() => setAdding((v) => !v)}
          className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
        >
          <Plus className="h-3 w-3" />
          Добавить
        </button>
      </div>

      <ul className="space-y-1.5">
        {contacts.map((contact) => (
          <li
            key={contact.id}
            className="flex items-center justify-between gap-2 rounded-md border px-2 py-1.5"
          >
            <div className="min-w-0">
              <p className="truncate text-xs font-medium">{contact.value}</p>
              <p className="text-[11px] text-muted-foreground">
                {CHANNEL_LABELS[contact.channel] || contact.channel}
                {contact.label ? ` · ${contact.label}` : ""}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {contact.is_primary && (
                <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                  основной
                </span>
              )}
              <button
                type="button"
                onClick={() => remove.mutate(contact.id)}
                disabled={remove.isPending}
                title="Удалить контакт"
                className="flex h-6 w-6 items-center justify-center rounded text-gray-300 hover:bg-red-50 hover:text-red-600"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </li>
        ))}
        {contacts.length === 0 && (
          <li className="text-xs text-muted-foreground">Контактов нет</li>
        )}
      </ul>

      {adding && (
        <div className="space-y-2 rounded-md border p-2">
          <select
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
            className="w-full rounded-md border bg-background px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="email">Почта</option>
            <option value="phone">Телефон</option>
            <option value="telegram">Telegram</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="vk">ВКонтакте</option>
            <option value="avito">Авито</option>
          </select>
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={
              channel === "email"
                ? "mail@example.com"
                : channel === "telegram"
                  ? "@username"
                  : "+79001234567"
            }
            className="w-full rounded-md border bg-background px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-ring"
          />
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Подпись (необязательно)"
            className="w-full rounded-md border bg-background px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-ring"
          />
          <div className="flex gap-2">
            <button
              onClick={() => add.mutate()}
              disabled={!value || add.isPending}
              className="rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground disabled:opacity-50"
            >
              {add.isPending ? "…" : "Сохранить"}
            </button>
            <button
              onClick={() => setAdding(false)}
              className="rounded-md border px-3 py-1.5 text-xs"
            >
              Отмена
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------- Лента сообщений ---------- */

function Thread({
  conversation,
}: {
  conversation: ConversationDetail;
}) {
  const queryClient = useQueryClient();
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
  const [channel, setChannel] = useState<string>("");
  const [pendingFiles, setPendingFiles] = useState<MessageAttachment[]>([]);
  const [uploading, setUploading] = useState(false);

  const uploadFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", file);
        const { data } = await api.post<MessageAttachment>(
          `/conversations/${conversation.id}/attachments`,
          form,
          { headers: { "Content-Type": "multipart/form-data" } }
        );
        setPendingFiles((prev) => [...prev, data]);
      }
    } catch (error) {
      toast({
        title: "Не удалось загрузить файл",
        description: apiErrorMessage(error, "Ошибка загрузки"),
      });
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const sendable = useMemo(() => {
    const seen = new Set<string>();
    const out: ContactPoint[] = [];
    for (const contact of conversation.contacts) {
      if (!SENDABLE_CHANNELS.has(contact.channel)) continue;
      if (seen.has(contact.channel)) continue;
      seen.add(contact.channel);
      out.push(contact);
    }
    return out;
  }, [conversation.contacts]);

  const hiddenByChannel = useMemo(() => {
    const hidden = new Set<string>();
    for (const contact of conversation.contacts) {
      if (!SENDABLE_CHANNELS.has(contact.channel)) hidden.add(contact.channel);
    }
    return hidden;
  }, [conversation.contacts]);

  // Переключение диалога: сбрасываем канал и черновик. Иначе канал,
  // выбранный в прошлом чате, остаётся здесь — отправка уходит не туда
  // или падает с «У клиента нет контакта в канале».
  useEffect(() => {
    setChannel("");
    setText("");
    setPendingFiles([]);
  }, [conversation.id]);

  useEffect(() => {
    if (sendable.length === 0) return;
    if (!channel || !sendable.some((c) => c.channel === channel)) {
      const primary = sendable.find((c) => c.is_primary) || sendable[0];
      setChannel(primary.channel);
    }
  }, [sendable, channel]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversation.messages.length]);

  const send = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ ok: boolean; note?: string | null }>(
        `/conversations/${conversation.id}/messages`,
        {
          channel,
          content: text,
          attachments: pendingFiles.map((f) => f.url),
        }
      );
      return data;
    },
    onSuccess: (res) => {
      setText("");
      setPendingFiles([]);
      if (res?.note) {
        toast({ title: "Не доставлено", description: res.note });
      }
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      queryClient.invalidateQueries({ queryKey: ["conversation", conversation.id] });
    },
    onError: (error: { response?: { data?: { detail?: unknown } } }) => {
      toast({
        title: "Не удалось отправить",
        description: apiErrorMessage(error, "Ошибка отправки"),
      });
    },
  });

  const canSend =
    Boolean((text.trim() || pendingFiles.length > 0) && channel) &&
    !send.isPending &&
    !uploading;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {conversation.messages.length === 0 && (
          <p className="text-center text-sm text-muted-foreground">
            Сообщений пока нет
          </p>
        )}

        {conversation.messages.map((message, index) => {
          const outbound = message.direction === "outbound";
          const unread = !outbound && !message.is_read;
          const prev = index > 0 ? conversation.messages[index - 1] : null;
          const prevUnread = Boolean(
            prev && prev.direction === "inbound" && !prev.is_read
          );
          return (
            <Fragment key={message.id}>
              {unread && !prevUnread && (
                <div className="flex items-center gap-2 text-[11px] font-medium text-primary">
                  <span className="h-px flex-1 bg-primary/30" />
                  <span>Новые сообщения</span>
                  <span className="h-px flex-1 bg-primary/30" />
                </div>
              )}
              <div
                className={cn(
                  "flex",
                  outbound ? "justify-end" : "justify-start"
                )}
              >
                <div
                  className={cn(
                    "max-w-[80%] rounded-lg px-3 py-2",
                    outbound
                      ? "bg-primary text-primary-foreground"
                      : unread
                        ? "bg-background ring-2 ring-primary/40"
                        : "bg-muted"
                  )}
                >
                  {message.subject && (
                    <p className="mb-1 text-[11px] opacity-70">
                      {message.subject}
                    </p>
                  )}
                  {message.content && (
                    <p className="whitespace-pre-wrap break-words text-sm">
                      {message.content}
                    </p>
                  )}
                  {(message.attachments || []).length > 0 && (
                    <div
                      className={cn(
                        "space-y-1.5",
                        message.content ? "mt-1.5" : ""
                      )}
                    >
                      {(message.attachments || []).map((attachment) => {
                        const isImage =
                          (attachment.content_type || "").startsWith("image/") ||
                          /\.(jpe?g|png|webp|gif|avif)$/i.test(attachment.url);
                        const href = /^https?:\/\//.test(attachment.url)
                          ? attachment.url
                          : `${API_URL}${attachment.url}`;
                        if (isImage) {
                          return (
                            <a
                              key={attachment.url}
                              href={href}
                              target="_blank"
                              rel="noreferrer"
                              className="block"
                            >
                              <img
                                src={href}
                                alt={attachment.name || "изображение"}
                                loading="lazy"
                                className="max-h-52 max-w-full rounded-md bg-background/40 object-contain"
                              />
                            </a>
                          );
                        }
                        return (
                          <a
                            key={attachment.url}
                            href={href}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-current/30 px-2 py-1 text-xs underline-offset-2 hover:underline"
                            title={attachment.name || "Открыть файл"}
                          >
                            <Paperclip className="h-3.5 w-3.5 shrink-0" />
                            <span className="truncate">
                              {attachment.name || "Вложение"}
                            </span>
                          </a>
                        );
                      })}
                    </div>
                  )}
                  <div className="mt-1 flex items-center gap-2 text-[10px] opacity-70">
                    <span>{formatTime(message.created_at)}</span>
                    <span className="inline-flex items-center gap-1">
                      <ChannelIcon channel={message.channel} className="h-3 w-3" />
                      {CHANNEL_LABELS[message.channel] || message.channel}
                    </span>
                    {outbound && message.author_name && (
                      <span>{message.author_name}</span>
                    )}
                    {unread && (
                      <span className="font-medium">не прочитано</span>
                    )}
                    {outbound && message.delivered === false && (
                      <span className="font-semibold">не доставлено</span>
                    )}
                  </div>
                </div>
              </div>
            </Fragment>
          );
        })}

        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (canSend) send.mutate();
        }}
        className="border-t p-3"
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.csv,.txt,.zip,.heic,.mp3,.ogg,.m4a,.mp4"
          onChange={(e) => uploadFiles(e.target.files)}
        />
        {pendingFiles.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {pendingFiles.map((file, index) => (
              <span
                key={file.url}
                className="inline-flex max-w-[14rem] items-center gap-1 rounded-md border bg-muted px-2 py-1 text-xs"
              >
                <Paperclip className="h-3 w-3 shrink-0 text-muted-foreground" />
                <span className="truncate">{file.name}</span>
                <button
                  type="button"
                  onClick={() =>
                    setPendingFiles((prev) =>
                      prev.filter((_, idx) => idx !== index)
                    )
                  }
                  title="Убрать файл"
                  className="shrink-0 rounded text-muted-foreground hover:text-red-600"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        )}
        {uploading && (
          <p className="mb-1.5 text-[11px] text-muted-foreground">
            Загрузка файла…
          </p>
        )}
        <div className="flex gap-2">
          <select
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
            className="w-36 shrink-0 rounded-md border bg-background px-2 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            title="Куда отправлять"
          >
            {sendable.length === 0 && <option value="">Нет контактов</option>}
            {sendable.map((contact) => (
              <option key={contact.channel} value={contact.channel}>
                {CHANNEL_LABELS[contact.channel] || contact.channel}
              </option>
            ))}
          </select>
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={
              pendingFiles.length > 0
                ? "Подпись к вложению…"
                : "Написать сообщение…"
            }
            className="min-w-0 flex-1 rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            title="Прикрепить файл"
            className="flex shrink-0 items-center justify-center rounded-md border bg-background px-2.5 text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Paperclip className="h-4 w-4" />
          </button>
          <CannedRepliesMenu
            onPick={(canned) =>
              setText((prev) => (prev ? `${prev}\n${canned}` : canned))
            }
          />
          <button
            type="submit"
            disabled={!canSend}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground disabled:hover:bg-muted"
            title="Отправить"
          >
            <Send className="h-4 w-4" />
            Ответить
          </button>
        </div>
        {sendable.length === 0 && hiddenByChannel.size > 0 && (
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            Отправлять можно в почту, Telegram, ВКонтакте и Авито — по
            {Array.from(hiddenByChannel)
              .map((c) => ` «${CHANNEL_LABELS[c] || c}»`)
              .join(", ")}{" "}
            отправка недоступна
          </p>
        )}
        {sendable.length === 0 && hiddenByChannel.size === 0 && (
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            Добавьте контакт клиента, чтобы отправлять сообщения
          </p>
        )}
      </form>
    </div>
  );
}

/* ---------- Страница ---------- */

export default function MessagesPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [showContacts, setShowContacts] = useState(false);
  const [archivedView, setArchivedView] = useState(false);

  const { data: conversation } = useQuery({
    queryKey: ["conversation", selectedId],
    queryFn: async () => {
      const { data } = await api.get<ConversationDetail>(
        `/conversations/${selectedId}`
      );
      return data;
    },
    enabled: Boolean(selectedId),
    // Пока диалог открыт, новые сообщения должны появляться сами
    refetchInterval: 10000,
  });

  const read = useMutation({
    mutationFn: async (id: string) => {
      await api.post(`/conversations/${id}/read`);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      queryClient.invalidateQueries({ queryKey: ["conversation"] });
    },
  });

  const readAll = useMutation({
    mutationFn: async () => {
      await api.post("/conversations/read-all");
    },
    onSuccess: () => {
      toast({ title: "Все диалоги отмечены прочитанными" });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      queryClient.invalidateQueries({ queryKey: ["conversation"] });
    },
  });

  const toggleStatus = useMutation({
    mutationFn: async (id: string) => {
      const next = conversation?.status === "closed" ? "open" : "close";
      await api.post(`/conversations/${id}/${next === "open" ? "open" : "close"}`);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      queryClient.invalidateQueries({ queryKey: ["conversation"] });
    },
  });

  const toggleArchive = useMutation({
    mutationFn: async (id: string) => {
      const action = conversation?.is_archived ? "unarchive" : "archive";
      await api.post(`/conversations/${id}/${action}`);
    },
    onSuccess: () => {
      if (conversation?.is_archived) {
        toast({ title: "Чат возвращён из архива" });
      } else {
        toast({ title: "Чат скрыт", description: "Найти его можно во вкладке «Архив»" });
        setSelectedId(null);
      }
    },
    onError: (error: { response?: { data?: { detail?: string } } }) => {
      toast({
        title: "Не удалось изменить статус чата",
        description: apiErrorMessage(error, "Ошибка сохранения"),
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      queryClient.invalidateQueries({ queryKey: ["conversation"] });
    },
  });

  useEffect(() => {
    if (selectedId) read.mutate(selectedId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  // Пока диалог открыт, входящие помечаем прочитанными — счётчик гаснет
  useEffect(() => {
    if (!conversation) return;
    const hasUnread = conversation.messages.some(
      (m) => m.direction === "inbound" && !m.is_read
    );
    if (hasUnread && !read.isPending) read.mutate(conversation.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversation?.messages]);

  const openedMessages = conversation?.messages ?? [];
  const awaitingReply =
    openedMessages.length > 0 &&
    openedMessages[openedMessages.length - 1].direction === "inbound";

  return (
    <div className="flex h-[calc(100vh-7rem)] gap-4">
      <aside
        className={cn(
          "flex w-full flex-col rounded-lg border md:w-80",
          selectedId && "hidden md:flex"
        )}
      >
        <div className="space-y-2 border-b p-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск по имени или контакту"
              className="w-full rounded-md border bg-background py-2 pl-8 pr-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div className="flex flex-wrap gap-1">
            {[
              { key: "all", label: "Все" },
              { key: "active", label: "В аренде" },
              { key: "closed", label: "Без сделки" },
            ].map((item) => (
              <button
                key={item.key}
                onClick={() => {
                  setFilter(item.key);
                  setArchivedView(false);
                }}
                className={cn(
                  "whitespace-nowrap rounded-md px-2.5 py-1 text-xs font-medium",
                  filter === item.key && !archivedView
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-muted"
                )}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-1">
            <button
              onClick={() => {
                // «Архив» и обычные фильтры взаимоисключающие:
                // вход в архив сбрасывает фильтр, любой фильтр выходит из архива
                if (archivedView) {
                  setArchivedView(false);
                } else {
                  setFilter("all");
                  setArchivedView(true);
                }
              }}
              className={cn(
                "inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2.5 py-1 text-xs font-medium",
                archivedView
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted"
              )}
              title={
                archivedView ? "Вернуться к активным чатам" : "Скрытые чаты"
              }
            >
              <Archive className="h-3.5 w-3.5" />
              Архив
            </button>
            <button
              onClick={() => readAll.mutate()}
              disabled={readAll.isPending}
              className="inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-muted disabled:opacity-50"
              title="Отметить все диалоги прочитанными"
            >
              <CheckCheck className="h-3.5 w-3.5" />
              Прочитать все
            </button>
            <button
              onClick={() => {
                queryClient.invalidateQueries({ queryKey: ["conversations"] });
                queryClient.invalidateQueries({ queryKey: ["conversation"] });
              }}
              className="ml-auto inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-muted"
              title="Обновить сообщения"
            >
              <RotateCw className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <ConversationList
            search={search}
            filter={filter}
            archived={archivedView}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onMarkRead={(id) => read.mutate(id)}
          />
        </div>
      </aside>

      <section
        className={cn(
          "min-w-0 flex-1 rounded-lg border",
          !selectedId && "hidden md:flex md:items-center md:justify-center"
        )}
      >
        {!selectedId && (
          <p className="text-sm text-muted-foreground">
            Выберите диалог слева
          </p>
        )}

        {selectedId && conversation && (
          <div className="flex h-full min-h-0 w-full flex-col">
            <header className="flex items-start justify-between gap-3 border-b px-4 py-3 pr-11">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setSelectedId(null)}
                    className="md:hidden"
                    title="Назад"
                  >
                    <ArrowLeft className="h-5 w-5" />
                  </button>
                  <h2 className="truncate text-sm font-semibold">
                    {conversation.customer_name}
                  </h2>
                  {awaitingReply && <AwaitingBadge />}
                  <DealBadge state={conversation.deal_state} />
                  {conversation.status === "closed" && (
                    <span className="inline-flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
                      <Lock className="h-3 w-3" />
                      закрыт
                    </span>
                  )}
                  {conversation.is_archived && (
                    <span className="inline-flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
                      <Archive className="h-3 w-3" />
                      в архиве
                    </span>
                  )}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  {conversation.customer_phone && <span>{conversation.customer_phone}</span>}
                  {conversation.customer_email && <span>{conversation.customer_email}</span>}
                  {conversation.lead_id && (
                    <a
                      href={`/orders?lead=${conversation.lead_id}`}
                      className="text-primary hover:underline"
                    >
                      Открыть сделку
                    </a>
                  )}
                </div>
              </div>

              <div className="flex shrink-0 items-center gap-2">
                <button
                  onClick={() => setShowContacts((v) => !v)}
                  className="rounded-md border px-2 py-1 text-xs"
                  title="Контакты клиента"
                >
                  <User className="inline h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => toggleStatus.mutate(conversation.id)}
                  className="rounded-md border px-2 py-1 text-xs"
                  title={
                    conversation.status === "closed"
                      ? "Открыть чат"
                      : "Закрыть чат"
                  }
                >
                  {conversation.status === "closed" ? (
                    <Unlock className="inline h-3.5 w-3.5" />
                  ) : (
                    <Lock className="inline h-3.5 w-3.5" />
                  )}
                </button>
                <button
                  onClick={() => toggleArchive.mutate(conversation.id)}
                  disabled={toggleArchive.isPending}
                  className="rounded-md border px-2 py-1 text-xs"
                  title={
                    conversation.is_archived
                      ? "Вернуть из архива"
                      : "Скрыть чат из ленты"
                  }
                >
                  <Archive
                    className={cn(
                      "inline h-3.5 w-3.5",
                      conversation.is_archived && "fill-current"
                    )}
                  />
                </button>
              </div>
            </header>

            <div className="grid min-h-0 flex-1 md:grid-cols-[1fr_16rem]">
              <div className="min-h-0 overflow-hidden">
                <Thread conversation={conversation} />
              </div>

              <aside
                className={cn(
                  "border-t p-3 md:border-l md:border-t-0",
                  showContacts ? "block" : "hidden md:block"
                )}
              >
                <ContactsPanel
                  customerId={conversation.customer_id}
                  contacts={conversation.contacts}
                />
                <div className="mt-4 space-y-1 border-t pt-3 text-xs text-muted-foreground">
                  <p className="font-medium text-foreground">
                    {DEAL_LABELS[conversation.deal_state]}
                  </p>
                  {conversation.deal_state === "deal_closed" && (
                    <p>
                      Завершённая сделка сохранена в истории, байк свободен.
                      Новое сообщение создаст новую сделку.
                    </p>
                  )}
                  <p>
                    Каналов в чате:{" "}
                    {conversation.channels.length
                      ? conversation.channels
                          .map((c) => CHANNEL_LABELS[c] || c)
                          .join(", ")
                      : "нет"}
                  </p>
                </div>
              </aside>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}