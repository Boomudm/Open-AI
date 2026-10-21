"use client";

import { useFactoryIdParam } from "@/hooks/useFactoryIdParam";
import { api, type JobRow } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { DEFAULT_PAGE_SIZE } from "@/lib/types/pagination";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

const ACTIVE_STATUSES = new Set(["queued", "running", "pending"]);

function hasActiveJobs(jobs: JobRow[]): boolean {
  return jobs.some((j) => ACTIVE_STATUSES.has(j.status.toLowerCase()));
}

export type UseIngestJobsParams = {
  status?: string;
  page?: number;
  pageSize?: number;
  /** Expanded job receiving SSE — slows list poll while active */
  expandedJobId?: string | null;
};

export function useIngestJobs(params: UseIngestJobsParams = {}) {
  const factoryId = useFactoryIdParam();
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? DEFAULT_PAGE_SIZE;
  const offset = (page - 1) * pageSize;

  const query = useQuery({
    queryKey: queryKeys.ingestJobs({
      factory_id: factoryId,
      status: params.status,
      limit: pageSize,
      offset,
    }),
    queryFn: () =>
      api.jobs({
        factory_id: factoryId,
        status: params.status,
        limit: pageSize,
        offset,
      }),
    refetchInterval: (q) => {
      const jobs = q.state.data;
      if (params.expandedJobId && jobs) {
        const expanded = jobs.find((j) => j.job_id === params.expandedJobId);
        if (expanded && ACTIVE_STATUSES.has(expanded.status.toLowerCase())) {
          return 10_000;
        }
      }
      if (!params.status && jobs && hasActiveJobs(jobs)) return 3000;
      if (params.status && ACTIVE_STATUSES.has(params.status) && jobs?.length) {
        return 3000;
      }
      return false;
    },
  });

  const jobs = query.data ?? [];
  const hasNextPage = jobs.length >= pageSize;
  const queryClient = useQueryClient();
  const prevActiveIds = useRef<Set<string>>(new Set());

  useEffect(() => {
    const activeNow = new Set(
      jobs
        .filter((j) => ACTIVE_STATUSES.has(j.status.toLowerCase()))
        .map((j) => j.job_id)
    );
    const finished = [...prevActiveIds.current].some((id) => !activeNow.has(id));
    prevActiveIds.current = activeNow;
    if (finished) {
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    }
  }, [jobs, queryClient]);

  return {
    jobs,
    hasNextPage,
    page,
    pageSize,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    error: query.error ? String(query.error) : null,
    refresh: () => query.refetch(),
  };
}

/** Poll all jobs (no pagination) — used by dashboard activity feed */
export function useIngestJobsList() {
  const factoryId = useFactoryIdParam();

  const query = useQuery({
    queryKey: queryKeys.ingestJobs({ all: true, factory_id: factoryId }),
    queryFn: () => api.jobs({ limit: 200, factory_id: factoryId }),
    staleTime: 60_000,
  });

  return {
    jobs: query.data ?? [],
    isLoading: query.isLoading,
    error: query.error ? String(query.error) : null,
  };
}
