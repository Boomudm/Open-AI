"use client";

import { cn } from "@/lib/cn";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { Search, X } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Button } from "./Button";
import { Input } from "./Input";

export type FilterOption = {
  value: string;
  label: string;
};

export type FilterField = {
  key: string;
  label: string;
  type: "search" | "select" | "multiselect";
  options?: FilterOption[];
  placeholder?: string;
};

export type FilterBarProps = {
  fields: FilterField[];
  values: Record<string, string | string[]>;
  onChange: (key: string, value: string | string[]) => void;
  onClear?: () => void;
  className?: string;
  actions?: ReactNode;
  debounceMs?: number;
};

function SearchFilterInput({
  field,
  value,
  onChange,
  debounceMs,
}: {
  field: FilterField;
  value: string;
  onChange: (value: string) => void;
  debounceMs: number;
}) {
  const [draft, setDraft] = useState(value);
  const debounced = useDebouncedValue(draft, debounceMs);
  const searchId = `filter-${field.key}`;

  useEffect(() => {
    if (value !== draft && value !== debounced) {
      setDraft(value);
    }
  }, [value, draft, debounced]);

  useEffect(() => {
    if (debounced !== value) {
      onChange(debounced);
    }
  }, [debounced, value, onChange]);

  return (
    <div className="flex-1 min-w-[160px] max-w-xs">
      <label
        htmlFor={searchId}
        className="block text-[10px] font-mono uppercase tracking-wider text-spark-text-muted mb-1"
      >
        {field.label}
      </label>
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-spark-text-muted" />
        <Input
          id={searchId}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={field.placeholder ?? "Search…"}
          className="pl-8 font-mono text-sm"
        />
      </div>
    </div>
  );
}

export function FilterBar({
  fields,
  values,
  onChange,
  onClear,
  className,
  actions,
  debounceMs = 300,
}: FilterBarProps) {
  const toggleMulti = useCallback(
    (key: string, value: string) => {
      const current = values[key];
      const arr = Array.isArray(current) ? current : current ? [String(current)] : [];
      const next = arr.includes(value)
        ? arr.filter((v) => v !== value)
        : [...arr, value];
      onChange(key, next);
    },
    [values, onChange]
  );

  const hasActiveFilters = fields.some((f) => {
    const v = values[f.key];
    if (Array.isArray(v)) return v.length > 0;
    return Boolean(v);
  });

  return (
    <div
      className={cn(
        "flex flex-wrap items-end gap-3 p-3 border border-spark-border rounded-sm bg-spark-surface",
        className
      )}
    >
      {fields.map((field) => {
        if (field.type === "search") {
          return (
            <SearchFilterInput
              key={field.key}
              field={field}
              value={String(values[field.key] ?? "")}
              onChange={(next) => onChange(field.key, next)}
              debounceMs={debounceMs}
            />
          );
        }

        if (field.type === "select") {
          return (
            <div key={field.key} className="min-w-[140px]">
              <label className="block text-[10px] font-mono uppercase tracking-wider text-spark-text-muted mb-1">
                {field.label}
              </label>
              <select
                value={String(values[field.key] ?? "")}
                onChange={(e) => onChange(field.key, e.target.value)}
                className={cn(
                  "w-full h-9 px-2.5 text-sm font-mono rounded-sm",
                  "bg-spark-elevated border border-spark-border text-spark-text-primary",
                  "focus:outline-none focus:border-spark-accent spark-focus-ring"
                )}
              >
                <option value="">All</option>
                {(field.options ?? []).map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          );
        }

        if (field.type === "multiselect") {
          const selected = Array.isArray(values[field.key])
            ? (values[field.key] as string[])
            : values[field.key]
              ? [String(values[field.key])]
              : [];
          return (
            <div key={field.key} className="min-w-[160px]">
              <label className="block text-[10px] font-mono uppercase tracking-wider text-spark-text-muted mb-1">
                {field.label}
              </label>
              <div className="flex flex-wrap gap-1">
                {(field.options ?? []).map((opt) => {
                  const active = selected.includes(opt.value);
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      aria-pressed={active}
                      onClick={() => toggleMulti(field.key, opt.value)}
                      className={cn(
                        "px-2 py-0.5 text-[10px] font-mono uppercase tracking-wide rounded-sm border transition-colors",
                        active
                          ? "bg-spark-accent-muted text-spark-accent border-spark-accent/40"
                          : "bg-spark-elevated text-spark-text-secondary border-spark-border hover:border-spark-border-strong"
                      )}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        }

        return null;
      })}

      <div className="flex items-center gap-2 ml-auto">
        {hasActiveFilters && onClear && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onClear}
            leftIcon={<X className="h-3 w-3" />}
          >
            Clear
          </Button>
        )}
        {actions}
      </div>
    </div>
  );
}
