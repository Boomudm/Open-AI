/** Shared chat question length limits (keep in sync with AskRequest.max_length). */

export const QUESTION_MAX_LENGTH = 3000;
export const QUESTION_LONG_TEXT_CTA_THRESHOLD = 800;

export function clampQuestionLength(value: string): string {
  if (value.length <= QUESTION_MAX_LENGTH) return value;
  return value.slice(0, QUESTION_MAX_LENGTH);
}

export function questionLengthLabel(length: number): string {
  return `${length}/${QUESTION_MAX_LENGTH}`;
}

export function isQuestionNearLimit(length: number): boolean {
  return length >= QUESTION_LONG_TEXT_CTA_THRESHOLD;
}

export function isQuestionOverLimit(length: number): boolean {
  return length > QUESTION_MAX_LENGTH;
}
