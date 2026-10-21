import assert from "node:assert/strict";

import type { Source } from "@/lib/api";
import { useChatStore } from "@/stores/chatStore";

function resetStore(): void {
  useChatStore.getState().setSending(false);
  useChatStore.getState().resetForSession();
}

function testWorkSummaryLifecycle(): void {
  resetStore();

  try {
    const streamId = "asst-stream-work-summary";
    const finalId = "assistant-work-summary";
    const startedBefore = Date.now();

    useChatStore.getState().setSending(true);
    useChatStore.getState().startAssistantStream(streamId);

    const started = useChatStore.getState();
    assert.equal(started.streamStatus.phase, "routing");
    assert.deepEqual(started.streamStatus.visitedPhases, ["routing"]);
    assert.ok(started.streamStartedAt !== null);
    assert.ok(started.streamStartedAt >= startedBefore);
    assert.ok(started.streamStartedAt <= Date.now());

    useChatStore.getState().setStreamPhase("generating");
    useChatStore.getState().setStreamPhase("searching");

    const monotonic = useChatStore.getState().streamStatus;
    assert.equal(monotonic.phase, "generating");
    assert.deepEqual(monotonic.visitedPhases, ["routing", "generating"]);

    useChatStore.getState().applyStreamMeta({
      stream_phase: "generating",
      route: "rag",
      intent: "maintenance_question",
      pipeline: "machinery",
      agentic_tools_called: ["search_documents"],
    });
    useChatStore.getState().applyStreamMeta({
      routing_reason: "metadata-only-update",
    });

    const metadataOnly = useChatStore.getState().streamStatus;
    assert.equal(metadataOnly.phase, "generating");
    assert.equal(metadataOnly.route, "rag");
    assert.equal(metadataOnly.intent, "maintenance_question");
    assert.equal(metadataOnly.pipeline, "machinery");
    assert.deepEqual(metadataOnly.toolsCalled, ["search_documents"]);
    assert.deepEqual(metadataOnly.visitedPhases, ["routing", "generating"]);

    const sources: Source[] = [
      {
        doc_id: "doc-1",
        title: "Maintenance manual",
        page: 3,
        chunk_id: "chunk-1",
        score: 0.92,
      },
    ];
    useChatStore.getState().setPendingStreamSources(sources);
    const returnedId = useChatStore.getState().finalizeStream(
      streamId,
      {
        assistant_message_id: finalId,
        route: "rag",
        intent: "maintenance_question",
      },
      sources
    );

    assert.equal(returnedId, finalId);
    const completedMessage = useChatStore
      .getState()
      .messages.find((message) => message.id === finalId);
    assert.ok(completedMessage?.workSummary);
    assert.equal(completedMessage.workSummary.status.phase, "done");
    assert.deepEqual(completedMessage.workSummary.status.visitedPhases, [
      "routing",
      "generating",
      "citations",
    ]);
    assert.equal(completedMessage.workSummary.sourceCount, 1);
    assert.ok(completedMessage.workSummary.durationMs >= 0);

    const persistedSummary = completedMessage.workSummary;
    useChatStore.getState().setSending(false);

    const reset = useChatStore.getState();
    assert.equal(reset.streamStatus.phase, "idle");
    assert.deepEqual(reset.streamStatus.visitedPhases, []);
    assert.equal(reset.streamStartedAt, null);
    assert.deepEqual(reset.messages[0]?.workSummary, persistedSummary);
  } finally {
    resetStore();
  }
}

testWorkSummaryLifecycle();

console.log("chat store work summary tests passed");
