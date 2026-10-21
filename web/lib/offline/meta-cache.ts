import type { IndexedDocument, Machine } from "@/lib/api";
import { DEFAULT_OFFLINE_PREFS } from "@/lib/offline/config";
import { idbGet, idbPut } from "@/lib/offline/idb";
import type { DocumentMetaSnapshot, MachineMetaSnapshot } from "@/lib/offline/types";

export async function saveDocumentMeta(
  factoryId: string,
  documents: IndexedDocument[]
): Promise<void> {
  const snapshot: DocumentMetaSnapshot = {
    factory_id: factoryId,
    documents,
    synced_at: new Date().toISOString(),
  };
  await idbPut("document_meta", snapshot);
}

export async function getDocumentMeta(
  factoryId: string
): Promise<DocumentMetaSnapshot | undefined> {
  try {
    return await idbGet<DocumentMetaSnapshot>("document_meta", factoryId);
  } catch {
    return undefined;
  }
}

export async function getDocumentsForMachine(
  factoryId: string,
  machineId: string
): Promise<IndexedDocument[]> {
  const snap = await getDocumentMeta(factoryId);
  if (!snap) return [];
  return snap.documents.filter((d) => d.machine_id === machineId);
}

export function isMetaFresh(syncedAt: string | undefined): boolean {
  if (!syncedAt) return false;
  const ageMs = Date.now() - new Date(syncedAt).getTime();
  return ageMs < DEFAULT_OFFLINE_PREFS.metaMaxAgeHours * 60 * 60 * 1000;
}

export async function saveMachineMeta(factoryId: string, machines: Machine[]): Promise<void> {
  const snapshot: MachineMetaSnapshot = {
    factory_id: factoryId,
    machines,
    synced_at: new Date().toISOString(),
  };
  await idbPut("machine_meta", snapshot);
}

export async function getMachineMeta(
  factoryId: string
): Promise<MachineMetaSnapshot | undefined> {
  try {
    return await idbGet<MachineMetaSnapshot>("machine_meta", factoryId);
  } catch {
    return undefined;
  }
}
