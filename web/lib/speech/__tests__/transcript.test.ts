import {
  appendSegment,
  joinPrefix,
  mergeRecognitionResults,
  spokenText,
} from "@/lib/speechTranscript";

function assert(cond: boolean, msg: string): void {
  if (!cond) throw new Error(msg);
}

function testJoinPrefix() {
  assert(joinPrefix("", "สวัสดี") === "สวัสดี", "empty prefix returns spoken only");
  assert(joinPrefix("  ", "สวัสดี") === "สวัสดี", "whitespace prefix treated as empty");
  assert(joinPrefix("hello", "world") === "hello world", "prefix and spoken joined with space");
  assert(joinPrefix("hello ", " world") === "hello world", "trims extra whitespace");
  assert(joinPrefix("hello", "") === "hello", "empty spoken returns prefix");
}

function testInterimToFinal() {
  const first = mergeRecognitionResults("", [{ transcript: "สวัส", isFinal: false }], 0);
  assert(first.committed === "", "interim does not commit");
  assert(first.interim === "สวัส", "interim captured");

  const second = mergeRecognitionResults(first.committed, [{ transcript: "สวัสดี", isFinal: true }], 0);
  assert(second.committed === "สวัสดี", "final commits once");
  assert(second.interim === "", "interim cleared after final");
  assert(spokenText(second.committed, second.interim) === "สวัสดี", "no duplicate text");
}

function testMultipleFinalSegments() {
  const step1 = mergeRecognitionResults("", [{ transcript: "เครื่อง", isFinal: true }], 0);
  const step2 = mergeRecognitionResults(step1.committed, [{ transcript: "MC-001", isFinal: true }], 0);
  assert(step2.committed === "เครื่อง MC-001", "multiple finals accumulate");
}

function testInterimChangesBeforeFinal() {
  let committed = "";
  let interim = "";

  const events = [
    { results: [{ transcript: "เครื่", isFinal: false }], fromIndex: 0 },
    { results: [{ transcript: "เครื่อง", isFinal: false }], fromIndex: 0 },
    { results: [{ transcript: "เครื่องจักร", isFinal: true }], fromIndex: 0 },
  ];

  for (const event of events) {
    const merged = mergeRecognitionResults(committed, event.results, event.fromIndex);
    committed = merged.committed;
    interim = merged.interim;
  }

  assert(committed === "เครื่องจักร", "uses latest final value");
  assert(interim === "", "no leftover interim");
  assert(spokenText(committed, interim) === "เครื่องจักร", "display matches committed");
}

function testIncrementalFromIndex() {
  let committed = "";
  let interim = "";

  const first = mergeRecognitionResults(
    committed,
    [{ transcript: "หนึ่ง", isFinal: true }],
    0
  );
  committed = first.committed;
  interim = first.interim;
  assert(committed === "หนึ่ง", "first final committed");
  assert(interim === "", "no interim after first final");

  const second = mergeRecognitionResults(
    committed,
    [
      { transcript: "หนึ่ง", isFinal: true },
      { transcript: "สอง", isFinal: false },
    ],
    1
  );
  committed = second.committed;
  interim = second.interim;
  assert(committed === "หนึ่ง", "committed unchanged on interim only");
  assert(interim === "สอง", "new interim from index 1");

  const third = mergeRecognitionResults(
    committed,
    [
      { transcript: "หนึ่ง", isFinal: true },
      { transcript: "สองสาม", isFinal: true },
    ],
    1
  );
  committed = third.committed;
  interim = third.interim;
  assert(committed === "หนึ่ง สองสาม", "second final appended from index");
  assert(interim === "", "final clears interim");
}

function testAppendSegment() {
  assert(appendSegment("a", "b") === "a b", "joins with space");
  assert(appendSegment("", "b") === "b", "empty base");
  assert(appendSegment("a", "") === "a", "empty segment");
}

testJoinPrefix();
testInterimToFinal();
testMultipleFinalSegments();
testInterimChangesBeforeFinal();
testIncrementalFromIndex();
testAppendSegment();

console.log("speech transcript tests passed");
