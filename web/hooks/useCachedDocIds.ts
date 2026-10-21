"use client";

import { listCachedDocuments } from "@/lib/offline/document-cache";
import { subscribeSyncStatus } from "@/lib/offline/sync-manager";
import { useEffect, useState } from "react";

export function useCachedDocIds(): Set<string> {
  const [ids, setIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    const refresh = () => {
      void listCachedDocuments().then((rows) => {
        setIds(new Set(rows.map((r) => r.doc_id)));
      });
    };
    refresh();
    const unsub = subscribeSyncStatus(() => refresh());
    return unsub;
  }, []);

  return ids;
}
