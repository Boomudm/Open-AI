"use client";

import { JobsTable } from "@/components/ingest/JobsTable";
import { useIngestPageFilters } from "@/hooks/useIngestPageFilters";
import { Suspense, useState } from "react";

function IngestJobsContent() {
  const { statusFilter, setStatusFilter } = useIngestPageFilters();
  const [page, setPage] = useState(1);

  return (
    <JobsTable
      statusFilter={statusFilter}
      onStatusFilterChange={(status) => {
        setStatusFilter(status);
        setPage(1);
      }}
      page={page}
      onPageChange={setPage}
    />
  );
}

export function IngestJobsTab() {
  return (
    <div className="max-w-5xl mx-auto w-full space-y-4">
      <div>
        <h2 className="text-sm font-medium text-gemini-text dark:text-gemini-dark-text">
          งานนำเข้าเอกสาร
        </h2>
        <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted mt-0.5">
          ติดตามสถานะงานนำเข้าและประมวลผลเอกสาร
        </p>
      </div>
      <Suspense
        fallback={
          <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted py-8 text-center">
            กำลังโหลด…
          </p>
        }
      >
        <IngestJobsContent />
      </Suspense>
    </div>
  );
}
