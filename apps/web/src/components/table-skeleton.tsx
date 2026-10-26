import { Skeleton } from "@/components/ui/skeleton";

export function TableSkeleton({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-0 px-5 pb-4" aria-busy aria-label="Loading">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex items-center gap-4 border-b border-hairline py-3 last:border-0">
          {Array.from({ length: cols }).map((__, c) => (
            <Skeleton key={c} className="h-3.5" style={{ width: c === 0 ? "22%" : `${10 + ((r + c) % 3) * 4}%` }} />
          ))}
        </div>
      ))}
    </div>
  );
}
