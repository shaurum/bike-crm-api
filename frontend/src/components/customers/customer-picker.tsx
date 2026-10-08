"use client";

import { useEffect, useRef, useState } from "react";
import { Search, UserPlus, Check, Phone, Cake } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { customersApi } from "@/lib/api";
import { CustomerCreateDialog, type CreatedCustomer } from "@/components/customers/customer-create-dialog";
import { cn } from "@/lib/utils";

export interface PickedCustomer {
  id: string;
  full_name: string;
  phone: string;
  email: string | null;
}

interface Match extends PickedCustomer {
  document_type: string;
  passport_number: string | null;
  passport_series: string | null;
  birth_date: string | null;
  country: string;
  documents_count: number;
}

const DOC_LABELS: Record<string, string> = {
  passport_rf: "Паспорт РФ",
  foreign_passport: "Загранпаспорт",
  residence_permit: "РВП / ВНЖ",
  id_card: "ID-карта",
  driver_license: "Вод. удостоверение",
  other: "Другой документ",
};

function ageFrom(birth: string | null): number | null {
  if (!birth) return null;
  const d = new Date(birth);
  if (Number.isNaN(d.getTime())) return null;
  const now = new Date();
  let age = now.getFullYear() - d.getFullYear();
  const m = now.getMonth() - d.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < d.getDate())) age--;
  return age;
}

function passportOf(m: Match): string {
  if (!m.passport_number) return "паспорт не заполнен";
  const series = m.passport_series ? `${m.passport_series} ` : "";
  return `${series}${m.passport_number}`;
}

/**
 * Поиск клиента по базе: подсвечивает совпадения, если клиента нет —
 * предлагает создать нового.
 */
export function CustomerPicker({
  value,
  onChange,
  onTextChange,
  placeholder = "Начните вводить ФИО или телефон",
  autoFocus,
}: {
  value: PickedCustomer | null;
  onChange: (customer: PickedCustomer | null) => void;
  onTextChange?: (text: string) => void;
  placeholder?: string;
  autoFocus?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<Match[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (value) setQuery(value.full_name);
  }, [value]);

  useEffect(() => {
    if (value) return;
    const term = query.trim();
    if (term.length < 2) {
      setMatches([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    const timer = setTimeout(async () => {
      try {
        const res = await customersApi.list({ search: term, size: 8 });
        setMatches((res.data?.items ?? []) as Match[]);
      } catch {
        setMatches([]);
      } finally {
        setLoading(false);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [query, value]);

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const pick = (m: Match) => {
    onChange({
      id: m.id,
      full_name: m.full_name,
      phone: m.phone,
      email: m.email,
    });
    setQuery(m.full_name);
    setOpen(false);
  };

  const reset = () => {
    onChange(null);
    setQuery("");
    setMatches([]);
  };

  const created = (c: CreatedCustomer) => {
    onChange(c);
    setQuery(c.full_name);
    setCreateOpen(false);
  };

  const showList = open && !value && query.trim().length >= 2;

  return (
    <div className="space-y-2" ref={boxRef}>
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
            onTextChange?.(e.target.value);
            if (value) onChange(null);
          }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder}
          autoFocus={autoFocus}
          autoComplete="off"
          className="h-10 w-full rounded-md border border-input bg-background pl-8 pr-9 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        {value ? (
          <button
            type="button"
            onClick={reset}
            aria-label="Очистить"
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <span className="text-lg leading-none">&times;</span>
          </button>
        ) : null}
      </div>

      {value && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm">
          <Check className="h-4 w-4 text-green-700" aria-hidden />
          <span className="font-medium">{value.full_name}</span>
          <span className="text-muted-foreground">{value.phone}</span>
        </div>
      )}

      {showList && (
        <div className="max-h-72 overflow-y-auto rounded-md border bg-white shadow-sm">
          {loading && matches.length === 0 ? (
            <p className="p-3 text-sm text-muted-foreground">Ищем…</p>
          ) : matches.length === 0 ? (
            <div className="p-2">
              <p className="px-2 py-1.5 text-sm text-muted-foreground">
                Никого не нашли
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-full justify-start"
                onClick={() => setCreateOpen(true)}
              >
                <UserPlus className="mr-2 h-4 w-4" aria-hidden />
                Создать клиента
              </Button>
            </div>
          ) : (
            <ul className="divide-y">
              {matches.map((m) => {
                const age = ageFrom(m.birth_date);
                return (
                  <li key={m.id}>
                    <button
                      type="button"
                      onClick={() => pick(m)}
                      className="w-full px-3 py-2.5 text-left hover:bg-gray-50"
                    >
                      <p className="text-sm font-medium">{m.full_name}</p>
                      <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <Phone className="h-3 w-3" aria-hidden />
                          {m.phone}
                        </span>
                        {age != null && (
                          <span className="flex items-center gap-1">
                            <Cake className="h-3 w-3" aria-hidden />
                            {age} лет
                          </span>
                        )}
                        <span>{passportOf(m)}</span>
                      </p>
                      <p className="mt-1 flex flex-wrap gap-1">
                        {m.passport_number && (
                          <Badge variant="secondary" className="text-[10px]">
                            {DOC_LABELS[m.document_type] ?? m.document_type}
                          </Badge>
                        )}
                        {m.country && m.country !== "Россия" && (
                          <Badge variant="outline" className="text-[10px]">
                            {m.country}
                          </Badge>
                        )}
                        {m.documents_count > 0 && (
                          <Badge variant="outline" className="text-[10px]">
                            сканов: {m.documents_count}
                          </Badge>
                        )}
                      </p>
                    </button>
                  </li>
                );
              })}
              <li className="p-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className={cn("w-full justify-start")}
                  onClick={() => setCreateOpen(true)}
                >
                  <UserPlus className="mr-2 h-4 w-4" aria-hidden />
                  Клиента нет — создать
                </Button>
              </li>
            </ul>
          )}
        </div>
      )}

      <CustomerCreateDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        defaultName={query.trim()}
        onCreated={created}
      />
    </div>
  );
}