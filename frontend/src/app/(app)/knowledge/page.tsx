"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bold,
  BookOpen,
  Code,
  Eye,
  Heading2,
  Heading3,
  ImagePlus,
  Italic,
  Link2,
  List,
  ListOrdered,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Search,
  Strikethrough,
  TextQuote,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "@/hooks/use-toast";

import { kbApi, type KBArticle } from "@/lib/api";
import { apiErrorMessage, cn } from "@/lib/utils";
import MarkdownBody from "@/components/kb/markdown";

/* ---------- Диалог статьи ---------- */

function ArticleDialog({
  article,
  onClose,
}: {
  article: KBArticle | "new" | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const isNew = article === "new";
  const editing = !isNew && article ? (article as KBArticle) : null;

  const [title, setTitle] = useState(editing?.title ?? "");
  const [category, setCategory] = useState(editing?.category ?? "");
  const [content, setContent] = useState(editing?.content ?? "");
  const [isPinned, setIsPinned] = useState(editing?.is_pinned ?? false);
  const [preview, setPreview] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (article && article !== "new") {
      setTitle(article.title);
      setCategory(article.category ?? "");
      setContent(article.content);
      setIsPinned(article.is_pinned);
    } else if (article === "new") {
      setTitle("");
      setCategory("");
      setContent("");
      setIsPinned(false);
    }
    setPreview(false);
  }, [article]);

  const uploadImage = useMutation({
    mutationFn: async (file: File) => (await kbApi.uploadImage(file)).data,
    onSuccess: (res) => {
      const snippet = `![изображение](${res.url})`;
      const ta = textareaRef.current;
      if (ta) {
        const start = ta.selectionStart ?? content.length;
        const end = ta.selectionEnd ?? content.length;
        const next = content.slice(0, start) + snippet + content.slice(end);
        setContent(next);
        setTimeout(() => {
          ta.focus();
          const pos = start + snippet.length;
          ta.setSelectionRange(pos, pos);
        }, 0);
      } else {
        setContent((prev) => `${prev}\n${snippet}\n`);
      }
    },
    onError: (error: { response?: { data?: { detail?: string } } }) =>
      toast({
        title: "Ошибка",
        description: apiErrorMessage(error, "Не удалось загрузить картинку"),
      }),
  });

  // --- Вставки markdown в textarea -----------------------------------------
  const withEditor = (fn: (ta: HTMLTextAreaElement) => void) => {
    if (preview) {
      setPreview(false);
      requestAnimationFrame(() => {
        const ta = textareaRef.current;
        if (ta) fn(ta);
      });
    } else {
      const ta = textareaRef.current;
      if (ta) fn(ta);
    }
  };

  /** Оборачивает выделение маркером (**, *, ~~, `...`). */
  const wrapSel = (mark: string, placeholder: string) =>
    withEditor((ta) => {
      const start = ta.selectionStart ?? 0;
      const end = ta.selectionEnd ?? 0;
      const sel = content.slice(start, end) || placeholder;
      const next = content.slice(0, start) + mark + sel + mark + content.slice(end);
      setContent(next);
      ta.focus();
      const s = start + mark.length;
      ta.setSelectionRange(s, s + sel.length);
    });

  /** Добавляет префикс в начало строки (#, -, >, 1.). */
  const prefixLine = (prefix: string, placeholder: string) =>
    withEditor((ta) => {
      const start = ta.selectionStart ?? 0;
      const end = ta.selectionEnd ?? 0;
      const lineStart = content.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
      const sel = content.slice(start, end) || placeholder;
      const next = content.slice(0, lineStart) + prefix + sel + content.slice(end);
      setContent(next);
      ta.focus();
      ta.setSelectionRange(lineStart + prefix.length, lineStart + prefix.length + sel.length);
    });

  const insertLink = () =>
    withEditor((ta) => {
      const start = ta.selectionStart ?? 0;
      const end = ta.selectionEnd ?? 0;
      const sel = content.slice(start, end);
      const snippet = sel ? `[${sel}](https://)` : `[текст ссылки](https://)`;
      const next = content.slice(0, start) + snippet + content.slice(end);
      setContent(next);
      ta.focus();
      const urlStart = start + (sel ? snippet.length - 8 : snippet.length - 1);
      ta.setSelectionRange(sel ? start + 1 : start + 1, sel ? start + 1 + sel.length : start + 15);
      void urlStart;
    });

  const TOOL_BTNS: {
    key: string;
    title: string;
    icon: typeof Bold;
    run: () => void;
  }[] = [
    { key: "b", title: "Жирный", icon: Bold, run: () => wrapSel("**", "жирный") },
    { key: "i", title: "Курсив", icon: Italic, run: () => wrapSel("*", "курсив") },
    { key: "s", title: "Зачёркнутый", icon: Strikethrough, run: () => wrapSel("~~", "зачёркнуто") },
    { key: "h2", title: "Заголовок", icon: Heading2, run: () => prefixLine("## ", "Заголовок") },
    { key: "h3", title: "Подзаголовок", icon: Heading3, run: () => prefixLine("### ", "Подзаголовок") },
    { key: "ul", title: "Маркированный список", icon: List, run: () => prefixLine("- ", "пункт") },
    { key: "ol", title: "Нумерованный список", icon: ListOrdered, run: () => prefixLine("1. ", "пункт") },
    { key: "q", title: "Цитата", icon: TextQuote, run: () => prefixLine("> ", "цитата") },
    { key: "code", title: "Код", icon: Code, run: () => wrapSel("`", "код") },
    { key: "a", title: "Ссылка", icon: Link2, run: insertLink },
  ];

  const save = useMutation({
    mutationFn: async () => {
      const payload = {
        title: title.trim(),
        content,
        category: category.trim() || null,
        is_pinned: isPinned,
      };
      if (editing) return (await kbApi.update(editing.id, payload)).data;
      return (await kbApi.create(payload)).data;
    },
    onSuccess: () => {
      toast({ title: editing ? "Статья обновлена" : "Статья создана" });
      qc.invalidateQueries({ queryKey: ["kb"] });
      onClose();
    },
    onError: (error: { response?: { data?: { detail?: string } } }) =>
      toast({
        title: "Ошибка",
        description: apiErrorMessage(error, "Не удалось сохранить статью"),
      }),
  });

  if (!article) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-lg bg-background shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b px-5 py-3">
          <h3 className="font-semibold">{editing ? "Редактирование" : "Новая статья"}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto p-5">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Заголовок *"
            className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <div className="flex gap-3">
            <input
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="Раздел (например: Доставка, Оплата)"
              className="flex-1 rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <button
              type="button"
              onClick={() => setIsPinned(!isPinned)}
              className={cn(
                "inline-flex items-center gap-1 rounded-md border px-3 py-2 text-sm",
                isPinned && "border-primary bg-primary/10 text-primary"
              )}
              title="Закрепить сверху в списке"
            >
              <Pin className="h-4 w-4" />
              Закрепить
            </button>
          </div>
          {/* Панель форматирования */}
          <div className="flex flex-wrap items-center gap-0.5 rounded-t-md border border-b-0 bg-muted/40 px-1.5 py-1">
            {TOOL_BTNS.map((btn) => {
              const Icon = btn.icon;
              return (
                <button
                  key={btn.key}
                  type="button"
                  title={btn.title}
                  onClick={btn.run}
                  className="rounded p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <Icon className="h-4 w-4" />
                </button>
              );
            })}
            <span className="mx-1 h-5 w-px bg-border" />
            <button
              type="button"
              title="Загрузить картинку и вставить её в текст"
              onClick={() => fileRef.current?.click()}
              disabled={uploadImage.isPending}
              className="inline-flex items-center gap-1 rounded px-2 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
            >
              <ImagePlus className="h-4 w-4" />
              {uploadImage.isPending ? "Загрузка…" : "Картинка"}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) uploadImage.mutate(file);
                e.target.value = "";
              }}
            />
            <button
              type="button"
              onClick={() => setPreview(!preview)}
              className={cn(
                "ml-auto inline-flex items-center gap-1 rounded px-2 py-1.5 text-xs font-medium",
                preview ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <Eye className="h-4 w-4" />
              {preview ? "Редактор" : "Предпросмотр"}
            </button>
          </div>
          {preview ? (
            <div className="min-h-[16rem] rounded-md rounded-t-none border bg-background p-3">
              <MarkdownBody content={content || "_Пустой текст_"} />
            </div>
          ) : (
            <textarea
              ref={textareaRef}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={"Текст статьи…\n\n## Заголовок\n\n**Жирный**, *курсив*, списки, картинки — markdown."}
              rows={16}
              className="w-full resize-y rounded-b-md border bg-background px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          )}
        </div>
        <div className="flex justify-end gap-2 border-t px-5 py-3">
          <button
            onClick={onClose}
            className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-muted"
          >
            Отмена
          </button>
          <button
            onClick={() => save.mutate()}
            disabled={save.isPending || !title.trim()}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            {save.isPending ? "Сохраняем…" : "Сохранить"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---------- Просмотр статьи ---------- */

function ViewDialog({
  article,
  onClose,
  onEdit,
}: {
  article: KBArticle | null;
  onClose: () => void;
  onEdit: () => void;
}) {
  const qc = useQueryClient();

  const remove = useMutation({
    mutationFn: async () => (await kbApi.remove(article!.id)).data,
    onSuccess: () => {
      toast({ title: "Статья удалена" });
      qc.invalidateQueries({ queryKey: ["kb"] });
      onClose();
    },
    onError: (error: { response?: { data?: { detail?: string } } }) =>
      toast({
        title: "Ошибка",
        description: apiErrorMessage(error, "Не удалось удалить статью"),
      }),
  });

  if (!article) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-lg bg-background shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b px-5 py-3">
          <div>
            <h3 className="font-semibold">{article.title}</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {article.category && <span className="mr-2 rounded bg-muted px-1.5 py-0.5">{article.category}</span>}
              {new Date(article.updated_at).toLocaleString("ru-RU")}
            </p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">
          {article.content ? (
            <MarkdownBody content={article.content} />
          ) : (
            <p className="text-sm text-muted-foreground">Пустая статья</p>
          )}
        </div>
        <div className="flex justify-between border-t px-5 py-3">
          <button
            onClick={() => remove.mutate()}
            disabled={remove.isPending}
            className="inline-flex items-center gap-1 rounded-md border border-destructive/40 px-3 py-2 text-sm text-destructive hover:bg-destructive/10 disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" />
            {remove.isPending ? "Удаляем…" : "Удалить"}
          </button>
          <button
            onClick={onEdit}
            className="inline-flex items-center gap-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            <Pencil className="h-4 w-4" />
            Редактировать
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---------- Страница ---------- */

export default function KnowledgePage() {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [dialog, setDialog] = useState<"new" | KBArticle | null>(null);
  const [viewing, setViewing] = useState<KBArticle | null>(null);
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["kb", "list", search, category],
    queryFn: async () =>
      (
        await kbApi.list({
          size: 200,
          q: search || undefined,
          category: category || undefined,
        })
      ).data,
    refetchOnWindowFocus: false,
  });

  const { data: categories } = useQuery({
    queryKey: ["kb", "categories"],
    queryFn: async () => (await kbApi.categories()).data.items,
  });

  const togglePin = useMutation({
    mutationFn: async (article: KBArticle) =>
      (await kbApi.update(article.id, { is_pinned: !article.is_pinned })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["kb"] }),
    onError: (error: { response?: { data?: { detail?: string } } }) =>
      toast({
        title: "Ошибка",
        description: apiErrorMessage(error, "Не удалось изменить закрепление"),
      }),
  });

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold">
            <BookOpen className="h-5 w-5" />
            База знаний
          </h1>
          <p className="text-sm text-muted-foreground">
            Инструкции, правила и ответы для команды — все в одном месте.
          </p>
        </div>
        <button
          onClick={() => setDialog("new")}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
        >
          <Plus className="h-4 w-4" />
          Новая статья
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по заголовку и тексту…"
            className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        {categories && categories.length > 0 && (
          <div className="flex flex-wrap gap-1">
            <button
              onClick={() => setCategory(null)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium",
                !category ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
              )}
            >
              Все
            </button>
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setCategory(cat === category ? null : cat)}
                className={cn(
                  "rounded-full border px-3 py-1 text-xs font-medium",
                  category === cat ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
                )}
              >
                {cat}
              </button>
            ))}
          </div>
        )}
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Загрузка…</p>}

      {!isLoading && data && data.items.length === 0 && (
        <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
          {search || category ? "Ничего не найдено" : "Статей пока нет — создайте первую"}
        </div>
      )}

      {!isLoading && data && data.items.length > 0 && (
        <div className="space-y-2">
          {data.items.map((article) => (
            <div
              key={article.id}
              className={cn(
                "group flex cursor-pointer items-start justify-between gap-3 rounded-lg border p-4 transition-colors hover:bg-muted/50",
                article.is_pinned && "border-primary/40 bg-primary/5"
              )}
              onClick={() => setViewing(article)}
            >
              <div className="min-w-0">
                <p className="flex items-center gap-1.5 font-medium">
                  {article.is_pinned && <Pin className="h-3.5 w-3.5 shrink-0 text-primary" />}
                  {article.title}
                </p>
                <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
                  {article.content.replace(/\s+/g, " ").slice(0, 140) || "—"}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {article.category && <span className="mr-2 rounded bg-muted px-1.5 py-0.5">{article.category}</span>}
                  {new Date(article.updated_at).toLocaleDateString("ru-RU")}
                </p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  togglePin.mutate(article);
                }}
                className="shrink-0 rounded-md p-1.5 text-muted-foreground opacity-0 transition-opacity hover:bg-muted group-hover:opacity-100"
                title={article.is_pinned ? "Открепить" : "Закрепить"}
              >
                {article.is_pinned ? <PinOff className="h-4 w-4" /> : <Pin className="h-4 w-4" />}
              </button>
            </div>
          ))}
        </div>
      )}

      <ArticleDialog article={dialog} onClose={() => setDialog(null)} />
      <ViewDialog
        article={viewing}
        onClose={() => setViewing(null)}
        onEdit={() => {
          const article = viewing;
          setViewing(null);
          setDialog(article);
        }}
      />
    </div>
  );
}
