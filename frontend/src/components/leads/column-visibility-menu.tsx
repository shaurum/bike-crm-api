"use client";

import { useState } from "react";
import { Columns3, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

const STORAGE_KEY = "bike-crm-hidden-stages";

export function readHiddenStages(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function writeHiddenStages(ids: string[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  } catch {
    /* private mode */
  }
}

export function ColumnVisibilityMenu({
  stages,
  hidden,
  onChange,
}: {
  stages: { id: string; name: string; color: string }[];
  hidden: string[];
  onChange: (next: string[]) => void;
}) {
  const [open, setOpen] = useState(false);

  const toggle = (stageId: string) => {
    const next = hidden.includes(stageId)
      ? hidden.filter((id) => id !== stageId)
      : [...hidden, stageId];
    onChange(next);
    writeHiddenStages(next);
  };

  const showAll = () => {
    onChange([]);
    writeHiddenStages([]);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Columns3 className="mr-2 h-4 w-4" aria-hidden />
          Колонки
          {hidden.length > 0 && (
            <span className="ml-2 rounded-full bg-primary px-1.5 py-0.5 text-[11px] text-primary-foreground">
              {hidden.length}
            </span>
          )}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Видимые колонки</DialogTitle>
        </DialogHeader>

        <div className="space-y-1">
          {stages.map((stage) => {
            const isHidden = hidden.includes(stage.id);
            return (
              <label
                key={stage.id}
                className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 hover:bg-gray-100"
              >
                <input
                  type="checkbox"
                  checked={!isHidden}
                  onChange={() => toggle(stage.id)}
                  className="h-4 w-4 cursor-pointer accent-current"
                />
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ backgroundColor: stage.color }}
                  aria-hidden
                />
                <span
                  className={
                    isHidden
                      ? "truncate text-muted-foreground line-through"
                      : "truncate"
                  }
                >
                  {stage.name}
                </span>
              </label>
            );
          })}
        </div>

        <DialogFooter>
          <Button
            variant="ghost"
            size="sm"
            onClick={showAll}
            disabled={hidden.length === 0}
          >
            <RotateCcw className="mr-2 h-4 w-4" aria-hidden />
            Показать все
          </Button>
          <Button size="sm" onClick={() => setOpen(false)}>
            Готово
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}