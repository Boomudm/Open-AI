import { pickEvictionCandidates, prefetchScore, shouldPrefetchDocument } from "@/lib/offline/lru";

function assert(cond: boolean, msg: string): void {
  if (!cond) throw new Error(msg);
}

function testPickEviction() {
  const records = [
    { doc_id: "a", file_size_bytes: 50, last_accessed_at: "2026-01-01", access_count: 1 },
    { doc_id: "b", file_size_bytes: 50, last_accessed_at: "2026-06-01", access_count: 5 },
    { doc_id: "c", file_size_bytes: 50, last_accessed_at: "2026-03-01", access_count: 2 },
  ];
  const evict = pickEvictionCandidates(records, 100, 120, 50);
  assert(evict.includes("a"), "should evict low access first");
  assert(!evict.includes("b"), "should keep high access");
}

function testShouldPrefetch() {
  assert(
    shouldPrefetchDocument({
      ingest_status: "completed",
      file_size_bytes: 1_000_000,
      document_type: "machine_manual",
    }),
    "completed small file ok"
  );
  assert(
    !shouldPrefetchDocument({
      ingest_status: "pending",
      file_size_bytes: 1_000,
      document_type: "machine_manual",
    }),
    "pending skip"
  );
  assert(
    !shouldPrefetchDocument({
      ingest_status: "completed",
      file_size_bytes: 30_000_000,
      document_type: "machine_manual",
    }),
    "large file skip"
  );
}

function testPrefetchScore() {
  const high = prefetchScore({ document_type: "machine_manual", file_size_bytes: 1_000_000 }, 3);
  const low = prefetchScore({ document_type: "incident_report", file_size_bytes: 10_000_000 }, 0);
  assert(high > low, "manual with access beats large incident");
}

testPickEviction();
testShouldPrefetch();
testPrefetchScore();

console.log("offline lru tests passed");
