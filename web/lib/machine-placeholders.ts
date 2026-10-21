/**
 * Mock cover photos from `public/machines/placeholders/` (sourced from dexter.co.th demo set).
 * Shown when the machine has no uploaded cover image.
 *
 * Each machine gets a distinct image by ID (not by type) so demo cards do not repeat.
 */

const PLACEHOLDER_POOL = [
  "/machines/placeholders/001.jpg",
  "/machines/placeholders/002.jpg",
  "/machines/placeholders/003.jpg",
  "/machines/placeholders/004.jpg",
  "/machines/placeholders/005.jpg",
  "/machines/placeholders/006.jpg",
  "/machines/placeholders/007.jpg",
  "/machines/placeholders/008.jpg",
];

function _slotFromMachineId(machineId: string): number {
  const mc = machineId.match(/MC-(\d+)/i);
  if (mc) {
    return (parseInt(mc[1], 10) - 1) % PLACEHOLDER_POOL.length;
  }
  let hash = 0;
  for (let i = 0; i < machineId.length; i++) {
    hash = (hash + machineId.charCodeAt(i) * (i + 1)) % PLACEHOLDER_POOL.length;
  }
  return hash;
}

export function machinePlaceholderSrc(
  machineId: string,
  _machineType?: string | null
): string {
  return PLACEHOLDER_POOL[_slotFromMachineId(machineId)] ?? PLACEHOLDER_POOL[0];
}
