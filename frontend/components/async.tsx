"use client";

import * as React from "react";
import { Loader2, ServerCrash, TriangleAlert } from "lucide-react";

import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";

interface FetchState<T> {
  data?: T;
  error?: Error;
  loading: boolean;
}

/**
 * Minimal client-side data hook. Refetches whenever `deps` change or `reload`
 * is called. Every consumer therefore gets graceful loading / error states,
 * including a clear "backend not running" hint (ApiError.offline).
 */
export function useFetch<T>(
  fetcher: () => Promise<T>,
  deps: React.DependencyList,
): FetchState<T> & { reload: () => void } {
  const [state, setState] = React.useState<FetchState<T>>({ loading: true });
  const [tick, setTick] = React.useState(0);

  React.useEffect(() => {
    let alive = true;
    setState({ loading: true });
    fetcher()
      .then((data) => alive && setState({ data, loading: false }))
      .catch((error: Error) => alive && setState({ error, loading: false }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { ...state, reload: () => setTick((t) => t + 1) };
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <Loader2 className="size-4 animate-spin" />
      {label ?? "Loading…"}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
}: {
  error: Error;
  onRetry?: () => void;
}) {
  const offline = error instanceof ApiError && error.offline;
  const Icon = offline ? ServerCrash : TriangleAlert;
  return (
    <div className="flex flex-col items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm">
      <div className="flex items-center gap-2 font-medium text-amber-900">
        <Icon className="size-4" />
        {offline ? "Backend not reachable" : "Something went wrong"}
      </div>
      <p className="text-amber-800">{error.message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

/** Wraps a fetch state, rendering loading / error / content in turn. */
export function Async<T>({
  state,
  onRetry,
  children,
  loadingFallback,
}: {
  state: FetchState<T> & { reload?: () => void };
  onRetry?: () => void;
  children: (data: T) => React.ReactNode;
  loadingFallback?: React.ReactNode;
}) {
  if (state.loading) return <>{loadingFallback ?? <Spinner />}</>;
  if (state.error)
    return <ErrorState error={state.error} onRetry={onRetry ?? state.reload} />;
  if (state.data === undefined) return null;
  return <>{children(state.data)}</>;
}
