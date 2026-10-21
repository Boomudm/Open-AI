/** UI-only flag: mobile citation drawer opens only after explicit user action. */

let mobileUserInitiated = false;
const listeners = new Set<() => void>();

function notify() {
  for (const listener of listeners) {
    listener();
  }
}

export function markCitationUserInitiated() {
  mobileUserInitiated = true;
  notify();
}

export function isCitationUserInitiated() {
  return mobileUserInitiated;
}

export function resetCitationUserInitiated() {
  if (!mobileUserInitiated) return;
  mobileUserInitiated = false;
  notify();
}

export function subscribeCitationPresentation(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
