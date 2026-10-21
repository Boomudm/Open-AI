export type RecognitionSegment = {
  transcript: string;
  isFinal: boolean;
};

export function joinPrefix(prefix: string, spoken: string): string {
  const trimmedPrefix = prefix.trimEnd();
  const trimmedSpoken = spoken.trimStart();
  if (!trimmedPrefix) return trimmedSpoken;
  if (!trimmedSpoken) return trimmedPrefix;
  return `${trimmedPrefix} ${trimmedSpoken}`;
}

export function appendSegment(base: string, segment: string): string {
  const trimmedBase = base.trimEnd();
  const trimmedSegment = segment.trim();
  if (!trimmedSegment) return trimmedBase;
  if (!trimmedBase) return trimmedSegment;
  return `${trimmedBase} ${trimmedSegment}`;
}

export function spokenText(committed: string, interim: string): string {
  if (!interim.trim()) return committed;
  return appendSegment(committed, interim);
}

export function mergeRecognitionResults(
  committed: string,
  results: RecognitionSegment[],
  fromIndex: number
): { committed: string; interim: string } {
  let nextCommitted = committed;
  let interim = "";

  for (let i = fromIndex; i < results.length; i += 1) {
    const { transcript, isFinal } = results[i];
    const text = transcript ?? "";
    if (!text) continue;

    if (isFinal) {
      nextCommitted = appendSegment(nextCommitted, text);
      interim = "";
    } else {
      interim = text;
    }
  }

  return { committed: nextCommitted, interim };
}
