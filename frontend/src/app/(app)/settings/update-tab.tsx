"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Circle,
  Clock,
  Download,
  ExternalLink,
  Loader2,
  RefreshCw,
  RotateCcw,
  ScrollText,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "@/hooks/use-toast";
import { ReleaseInfo, systemApi, SystemVersion, UpdateStage } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { apiErrorMessage, cn } from "@/lib/utils";

/** Этапы установки в порядке выполнения скриптом обновления. */
const STEPS: { stage: UpdateStage; label: string }[] = [
  { stage: "checking", label: "Подготовка" },
  { stage: "downloading", label: "Скачивание" },
  { stage: "extracting", label: "Распаковка" },
  { stage: "copying", label: "Копирование файлов" },
  { stage: "building", label: "Сборка образов" },
  { stage: "migrating", label: "Миграции базы данных" },
  { stage: "restarting", label: "Перезапуск CRM" },
];

// Первая версия со скриптом, который умеет ставить выбранную версию
const VERSION_PICKER_SINCE = "v1.1.7";

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU", {
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatAgo(iso: string | null | undefined, now: number): string {
  if (!iso) return "ещё не выполнялась";
  const sec = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (sec < 60) return "только что";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} мин назад`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} ч назад`;
  return formatDate(iso);
}

function formatDuration(fromIso: string | null, toMs: number): string {
  if (!fromIso) return "";
  const sec = Math.max(0, Math.round((toMs - new Date(fromIso).getTime()) / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m > 0 ? `${m} мин ${s.toString().padStart(2, "0")} с` : `${s} с`;
}

function formatSize(bytes: number | null | undefined): string {
  if (bytes == null) return "";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
}

/** Сравнение тегов вида v1.2.3: >0 если a новее b. */
function compareTags(a: string, b: string): number {
  const parse = (tag: string) => tag.replace(/^v/, "").split(/[.-]/).map((p) => parseInt(p, 10) || 0);
  const pa = parse(a);
  const pb = parse(b);
  for (let i = 0; i < Math.max(pa.length, pb.length); i += 1) {
    const diff = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

function useNow(active: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), active ? 1000 : 30000);
    return () => clearInterval(timer);
  }, [active]);
  return now;
}

/* ---------- Ход установки ---------- */

function StepList({ data }: { data: SystemVersion }) {
  const currentIndex = STEPS.findIndex((s) => s.stage === data.stage);
  return (
    <ol className="space-y-1.5">
      {STEPS.map((step, index) => {
        const done = data.stage === "done" || (currentIndex >= 0 && index < currentIndex);
        const active = index === currentIndex;
        return (
          <li key={step.stage} className="flex items-center gap-2 text-sm">
            {done ? (
              <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600" aria-hidden />
            ) : active ? (
              <Loader2 className="h-4 w-4 shrink-0 animate-spin text-blue-600" aria-hidden />
            ) : (
              <Circle className="h-4 w-4 shrink-0 text-gray-300" aria-hidden />
            )}
            <span className={cn(active ? "font-medium" : done ? "text-gray-700" : "text-muted-foreground")}>
              {step.label}
            </span>
            {active && step.stage === "downloading" && data.download_percent != null && (
              <span className="text-xs text-muted-foreground">
                {data.download_percent}%
                {data.download_total
                  ? ` · ${formatSize(data.download_bytes)} из ${formatSize(data.download_total)}`
                  : ""}
              </span>
            )}
            {active && step.stage === "building" && (
              <span className="text-xs text-muted-foreground">обычно 1–5 минут</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function ProgressBar({ value, tone }: { value: number; tone: "blue" | "green" | "red" }) {
  return (
    <div
      className="h-2 w-full overflow-hidden rounded-full bg-gray-100"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value}
    >
      <div
        className={cn(
          "h-full rounded-full transition-all duration-700",
          tone === "blue" && "bg-blue-600",
          tone === "green" && "bg-green-600",
          tone === "red" && "bg-red-500"
        )}
        style={{ width: `${Math.min(100, Math.max(2, value))}%` }}
      />
    </div>
  );
}

function InstallStatus({
  data,
  offline,
  now,
  isAdmin,
  onCancel,
  onRetry,
  busy,
}: {
  data: SystemVersion;
  offline: boolean;
  now: number;
  isAdmin: boolean;
  onCancel: () => void;
  onRetry: (tag: string | null) => void;
  busy: boolean;
}) {
  if (data.updating) {
    return (
      <div className="space-y-3 rounded-lg border border-blue-200 bg-blue-50/60 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="flex items-center gap-2 font-medium text-blue-900">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            Устанавливается {data.target_tag ?? "обновление"}
          </p>
          <span className="text-xs text-blue-900/70">
            {Math.round(data.progress)}% · идёт {formatDuration(data.started_at, now)}
          </span>
        </div>
        <ProgressBar value={data.progress} tone="blue" />
        <StepList data={data} />
        <p className="text-xs text-blue-900/70">
          {offline
            ? "CRM перезапускается, связь вернётся через минуту. Страницу закрывать не нужно."
            : "Во время перезапуска CRM будет недоступна около минуты."}
        </p>
      </div>
    );
  }

  if (data.queued) {
    const tag = data.queued_tag === "latest" ? "последняя версия" : data.queued_tag;
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-blue-200 bg-blue-50/60 p-4">
        <div className="flex items-start gap-2">
          <Clock className="mt-0.5 h-4 w-4 shrink-0 text-blue-700" aria-hidden />
          <div>
            <p className="font-medium text-blue-900">В очереди: {tag}</p>
            <p className="text-xs text-blue-900/70">
              Установка начнётся при следующем запуске автообновления — в течение 5 минут.
            </p>
          </div>
        </div>
        {isAdmin && (
          <Button variant="outline" size="sm" onClick={onCancel} disabled={busy}>
            Отменить
          </Button>
        )}
      </div>
    );
  }

  if (data.stage === "error") {
    return (
      <div className="space-y-2 rounded-lg border border-red-200 bg-red-50 p-4">
        <p className="flex items-center gap-2 font-medium text-red-800">
          <XCircle className="h-4 w-4" aria-hidden />
          Не удалось установить {data.target_tag ?? "обновление"}
        </p>
        <p className="text-sm text-red-700">{data.error ?? data.note}</p>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs text-red-700/80">{formatDate(data.finished_at)}</span>
          {isAdmin && (
            <Button size="sm" variant="outline" onClick={() => onRetry(data.target_tag)} disabled={busy}>
              <RotateCcw className="mr-2 h-4 w-4" aria-hidden />
              Повторить
            </Button>
          )}
        </div>
      </div>
    );
  }

  if (data.stage === "done" && data.finished_at) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <span>
          {data.target_tag} установлена {formatDate(data.finished_at)}
          {data.started_at && ` · заняло ${formatDuration(data.started_at, new Date(data.finished_at).getTime())}`}
        </span>
      </div>
    );
  }

  return null;
}

/* ---------- Список версий ---------- */

function ReleaseChanges({ tag }: { tag: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["system", "release-changes", tag],
    queryFn: async () => (await systemApi.releaseChanges(tag)).data.changes,
    staleTime: Infinity,
  });
  if (isLoading) return <p className="text-xs text-muted-foreground">Загрузка изменений…</p>;
  if (error) return <p className="text-xs text-red-600">{apiErrorMessage(error, "Не удалось загрузить изменения")}</p>;
  if (!data || data.length === 0) return <p className="text-xs text-muted-foreground">Описание изменений не указано</p>;
  return (
    <ul className="list-disc space-y-0.5 pl-5 text-xs text-gray-700">
      {data.map((line, i) => (
        <li key={i}>{line}</li>
      ))}
    </ul>
  );
}

function ReleaseRow({
  release,
  current,
  isAdmin,
  disabled,
  onInstall,
}: {
  release: ReleaseInfo;
  current: string | null;
  isAdmin: boolean;
  disabled: boolean;
  onInstall: (release: ReleaseInfo) => void;
}) {
  const [open, setOpen] = useState(false);
  const newer = current ? compareTags(release.tag, current) > 0 : true;
  const action = release.is_current ? "Переустановить" : newer ? "Обновить" : "Откатить";

  return (
    <li className={cn("rounded-lg border p-3", release.is_current && "border-primary/60 bg-primary/5")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm font-semibold">{release.tag}</span>
            {release.is_current && <Badge>Текущая</Badge>}
            {release.is_latest && !release.is_current && <Badge variant="success">Последняя</Badge>}
            {release.prerelease && <Badge variant="warning">Тестовая</Badge>}
          </div>
          <p className="text-xs text-muted-foreground">
            {formatDate(release.published_at)}
            {release.size ? ` · ${formatSize(release.size)}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            Что нового
            <ChevronDown className={cn("ml-1 h-4 w-4 transition-transform", open && "rotate-180")} aria-hidden />
          </Button>
          {isAdmin && (
            <Button
              size="sm"
              variant={newer && !release.is_current ? "default" : "outline"}
              disabled={disabled || !release.installable}
              title={release.installable ? undefined : "В этой версии нет архива для установки"}
              onClick={() => onInstall(release)}
            >
              {action}
            </Button>
          )}
        </div>
      </div>
      {open && (
        <div className="mt-2 space-y-2 border-t pt-2">
          <ReleaseChanges tag={release.tag} />
          {release.url && (
            <a
              href={release.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              Страница релиза на GitHub
              <ExternalLink className="h-3 w-3" aria-hidden />
            </a>
          )}
        </div>
      )}
    </li>
  );
}

/* ---------- Вкладка ---------- */

export default function UpdateTab() {
  const queryClient = useQueryClient();
  const isAdmin = useAuthStore((state) => state.user?.role === "admin");
  const [confirm, setConfirm] = useState<ReleaseInfo | null>(null);
  const [showLog, setShowLog] = useState(false);
  const loadedTag = useRef<string | null | undefined>(undefined);
  const lastData = useRef<SystemVersion | null>(null);

  const version = useQuery({
    queryKey: ["system", "version"],
    queryFn: async () => (await systemApi.version()).data,
    // Во время установки следим часто; при перезапуске API ошибки ожидаемы
    refetchInterval: (query) => {
      const d = query.state.data ?? lastData.current;
      return d?.updating || d?.queued ? 2000 : 30000;
    },
    retry: false,
  });

  const data = version.data ?? lastData.current;
  if (version.data) lastData.current = version.data;
  const offline = Boolean(version.error) && Boolean(lastData.current?.updating);
  const now = useNow(Boolean(data?.updating));

  // Версия сменилась, пока страница открыта: старый интерфейс надо перезагрузить
  if (data && loadedTag.current === undefined) loadedTag.current = data.current_tag;
  const reloadNeeded =
    data != null && loadedTag.current !== undefined && data.current_tag !== loadedTag.current && !data.updating;

  const releases = useQuery({
    queryKey: ["system", "releases"],
    queryFn: async () => (await systemApi.releases()).data,
    staleTime: 10 * 60 * 1000,
  });

  const log = useQuery({
    queryKey: ["system", "update-log"],
    queryFn: async () => (await systemApi.log()).data.lines,
    enabled: isAdmin && showLog,
    refetchInterval: data?.updating ? 3000 : false,
  });

  const refreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ["system", "version"] });
  };

  const install = useMutation({
    mutationFn: async (tag: string | null) => (await systemApi.install(tag)).data,
    onSuccess: (res) => {
      setConfirm(null);
      toast({ title: res.ok ? "Установка запланирована" : "Недоступно", description: res.detail });
      refreshAll();
    },
    onError: (err) => toast({ title: "Не удалось", description: apiErrorMessage(err, "Ошибка запроса") }),
  });

  const cancel = useMutation({
    mutationFn: async () => (await systemApi.cancel()).data,
    onSuccess: () => {
      toast({ title: "Установка отменена" });
      refreshAll();
    },
    onError: (err) => toast({ title: "Не удалось", description: apiErrorMessage(err, "Ошибка запроса") }),
  });

  const setMode = useMutation({
    mutationFn: async (mode: "auto" | "manual") => (await systemApi.setUpdateMode(mode)).data,
    onSuccess: (res) => {
      toast({
        title: "Режим обновления изменён",
        description: res.mode === "auto" ? "Новые версии ставятся автоматически" : "Обновления только по кнопке",
      });
      refreshAll();
    },
    onError: (err) => toast({ title: "Ошибка", description: apiErrorMessage(err, "Не удалось изменить режим") }),
  });

  const recheck = useMutation({
    mutationFn: async () => {
      const res = await systemApi.releases(true);
      queryClient.setQueryData(["system", "releases"], res.data);
      await version.refetch();
      return res.data;
    },
    onError: (err) => toast({ title: "Не удалось проверить", description: apiErrorMessage(err, "GitHub недоступен") }),
  });

  if (!data) {
    return version.error ? (
      <p className="rounded-md bg-red-50 p-3 text-sm text-red-600">
        {apiErrorMessage(version.error, "Не удалось получить версию CRM")}
      </p>
    ) : (
      <p className="text-sm text-muted-foreground">Загрузка версии…</p>
    );
  }

  const mode = data.mode === "manual" ? "manual" : "auto";
  const latest = releases.data?.latest ?? data.remote_sha;
  const current = data.current_tag;
  const upToDate = Boolean(current && latest && current === latest);
  const busy = data.updating || data.queued || install.isPending;

  const confirmNewer = confirm && current ? compareTags(confirm.tag, current) > 0 : true;
  const confirmIsLatest = confirm?.tag === latest;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold">Обновление CRM</h2>
        <p className="text-sm text-muted-foreground">
          Версии берутся из релизов на GitHub. Скрипт автообновления на сервере проверяет их каждые
          5 минут и ставит выбранную версию: скачивает, собирает и перезапускает CRM.
        </p>
      </div>

      {reloadNeeded && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-800">
          <span>Установлена {data.current_tag}. Обновите страницу, чтобы загрузить новый интерфейс.</span>
          <Button size="sm" onClick={() => window.location.reload()}>
            <RefreshCw className="mr-2 h-4 w-4" aria-hidden />
            Обновить страницу
          </Button>
        </div>
      )}

      {/* Текущая версия */}
      <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center rounded-lg border p-4">
        <div className="space-y-1">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Текущая версия</p>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-2xl font-semibold">
              {current ?? (data.current_sha ? `#${data.current_sha}` : "неизвестна")}
            </span>
            {upToDate ? (
              <Badge variant="success">Последняя</Badge>
            ) : latest && current ? (
              <Badge variant="warning">Доступна {latest}</Badge>
            ) : null}
          </div>
          <p className="text-xs text-muted-foreground">
            Проверено {formatAgo(data.last_check, now)}
            {" · "}
            {mode === "auto" ? "ставится автоматически" : "ставится только вручную"}
          </p>
        </div>
        {isAdmin && (
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => recheck.mutate()} disabled={recheck.isPending}>
              <RefreshCw className={cn("mr-2 h-4 w-4", recheck.isPending && "animate-spin")} aria-hidden />
              Проверить
            </Button>
            {!upToDate && latest && (
              <Button onClick={() => install.mutate(null)} disabled={busy}>
                <Download className="mr-2 h-4 w-4" aria-hidden />
                Установить {latest}
              </Button>
            )}
          </div>
        )}
      </div>

      {!data.configured && (
        <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          На этой машине автообновление не настроено: установить версию отсюда не получится.
        </p>
      )}
      {data.configured && data.stale && (
        <p className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          Скрипт автообновления не запускался больше 20 минут. Проверьте, что ПК включён и в
          Планировщике заданий Windows активна задача BikeCrmAutoUpdate.
        </p>
      )}

      <InstallStatus
        data={data}
        offline={offline}
        now={now}
        isAdmin={isAdmin}
        busy={cancel.isPending || install.isPending}
        onCancel={() => cancel.mutate()}
        onRetry={(tag) => install.mutate(tag)}
      />

      {/* Режим */}
      {isAdmin && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
          <div>
            <p className="text-sm font-medium">Режим установки</p>
            <p className="text-xs text-muted-foreground">
              {mode === "auto"
                ? "Новые версии устанавливаются сами в течение 5 минут после выхода"
                : "Версии ставятся только по кнопке; удобно, если нужно остаться на старой версии"}
            </p>
          </div>
          <div className="flex shrink-0 gap-1 rounded-md border p-1">
            {(["auto", "manual"] as const).map((value) => (
              <button
                key={value}
                onClick={() => setMode.mutate(value)}
                disabled={setMode.isPending || data.updating}
                className={cn(
                  "rounded px-3 py-1 text-sm font-medium transition-colors disabled:opacity-50",
                  mode === value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
                )}
              >
                {value === "auto" ? "Авто" : "Вручную"}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Версии */}
      <section className="space-y-2">
        <h3 className="text-sm font-semibold">Версии</h3>
        {releases.isLoading && <p className="text-sm text-muted-foreground">Загрузка списка версий…</p>}
        {releases.error && (
          <p className="rounded-md bg-red-50 p-3 text-sm text-red-600">
            {apiErrorMessage(releases.error, "Не удалось загрузить список версий")}
          </p>
        )}
        {releases.data && (
          <ul className="space-y-2">
            {releases.data.items.map((release) => (
              <ReleaseRow
                key={release.tag}
                release={release}
                current={current}
                isAdmin={isAdmin}
                disabled={busy || !data.configured}
                onInstall={setConfirm}
              />
            ))}
          </ul>
        )}
      </section>

      {/* Журнал */}
      {isAdmin && (
        <section className="space-y-2">
          <button
            type="button"
            onClick={() => setShowLog((v) => !v)}
            className="flex items-center gap-2 text-sm font-semibold"
            aria-expanded={showLog}
          >
            <ScrollText className="h-4 w-4" aria-hidden />
            Журнал установки
            <ChevronDown className={cn("h-4 w-4 transition-transform", showLog && "rotate-180")} aria-hidden />
          </button>
          {showLog && (
            <pre className="max-h-72 overflow-auto rounded-lg bg-gray-950 p-3 text-xs leading-relaxed text-gray-100">
              {log.isLoading
                ? "Загрузка…"
                : log.data && log.data.length > 0
                  ? log.data.join("\n")
                  : "Журнал пуст"}
            </pre>
          )}
        </section>
      )}

      <Dialog open={confirm != null} onOpenChange={(open) => !open && setConfirm(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {confirm?.is_current
                ? `Переустановить ${confirm.tag}?`
                : confirmNewer
                  ? `Обновить до ${confirm?.tag}?`
                  : `Откатить до ${confirm?.tag}?`}
            </DialogTitle>
            <DialogDescription>
              Установка начнётся в течение 5 минут. CRM будет недоступна около минуты во время
              перезапуска.
            </DialogDescription>
          </DialogHeader>
          {confirm && !confirmNewer && !confirm.is_current && (
            <div className="space-y-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              <p>
                База данных не откатывается: если в более новой версии менялась её структура,
                старая версия может работать с ошибками.
              </p>
              {mode === "auto" && <p>Режим переключится на «Вручную», чтобы CRM не обновилась обратно.</p>}
              {compareTags(confirm.tag, VERSION_PICKER_SINCE) < 0 && (
                <p>
                  В {confirm.tag} ещё нет выбора версии: вернуться можно кнопкой «Проверить и
                  установить» — она поставит последнюю версию.
                </p>
              )}
            </div>
          )}
          {confirm && confirmIsLatest && !confirm.is_current && mode === "manual" && (
            <p className="text-xs text-muted-foreground">
              Режим останется «Вручную»: следующие версии ставьте так же кнопкой.
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm(null)}>
              Отмена
            </Button>
            <Button onClick={() => confirm && install.mutate(confirm.tag)} disabled={install.isPending}>
              {install.isPending ? "Запрос…" : "Установить"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
