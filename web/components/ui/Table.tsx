import { cn } from "@/lib/cn";
import { MSG_NO_DATA } from "@/lib/messages.th";
import type { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";

export function Table({ className, ...props }: HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto border border-spark-border rounded-sm">
      <table
        className={cn("w-full text-sm border-collapse font-sans", className)}
        {...props}
      />
    </div>
  );
}

export function TableHeader({
  className,
  ...props
}: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead
      className={cn("bg-spark-elevated border-b border-spark-border", className)}
      {...props}
    />
  );
}

export function TableBody({
  className,
  ...props
}: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("divide-y divide-spark-border", className)} {...props} />;
}

export function TableRow({
  className,
  ...props
}: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={cn(
        "transition-colors duration-fast hover:bg-spark-hover/50",
        className
      )}
      {...props}
    />
  );
}

export function TableHead({
  className,
  ...props
}: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        "px-3 py-2 text-left text-xs font-mono uppercase tracking-wider",
        "text-spark-text-secondary font-medium whitespace-nowrap",
        className
      )}
      {...props}
    />
  );
}

export function TableCell({
  className,
  ...props
}: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td
      className={cn(
        "px-3 py-2 text-sm text-spark-text-primary tabular-nums",
        className
      )}
      {...props}
    />
  );
}

export function TableEmpty({
  message = MSG_NO_DATA,
  colSpan = 1,
}: {
  message?: string;
  colSpan?: number;
}) {
  return (
    <TableRow>
      <TableCell
        colSpan={colSpan}
        className="py-8 text-center text-spark-text-secondary font-mono text-xs"
      >
        {message}
      </TableCell>
    </TableRow>
  );
}
