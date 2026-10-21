const DB_NAME = "spark-offline";
const DB_VERSION = 2;

export type SparkOfflineDB = {
  document_blobs: {
    key: string;
    value: unknown;
  };
  document_meta: {
    key: string;
    value: unknown;
  };
  machine_meta: {
    key: string;
    value: unknown;
  };
  feedback_outbox: {
    key: string;
    value: unknown;
  };
  offline_prefs: {
    key: string;
    value: unknown;
  };
};

let dbPromise: Promise<IDBDatabase> | null = null;

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof indexedDB !== "undefined";
}

export function openOfflineDb(): Promise<IDBDatabase> {
  if (!isBrowser()) {
    return Promise.reject(new Error("IndexedDB unavailable"));
  }
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onerror = () => reject(req.error ?? new Error("idb open failed"));
      req.onsuccess = () => resolve(req.result);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains("document_blobs")) {
          db.createObjectStore("document_blobs", { keyPath: "doc_id" });
        }
        if (!db.objectStoreNames.contains("document_meta")) {
          db.createObjectStore("document_meta", { keyPath: "factory_id" });
        }
        if (!db.objectStoreNames.contains("machine_meta")) {
          db.createObjectStore("machine_meta", { keyPath: "factory_id" });
        }
        if (!db.objectStoreNames.contains("feedback_outbox")) {
          db.createObjectStore("feedback_outbox", { keyPath: "local_id" });
        }
        if (!db.objectStoreNames.contains("offline_prefs")) {
          db.createObjectStore("offline_prefs", { keyPath: "key" });
        }
      };
    });
  }
  return dbPromise;
}

export async function idbGet<T>(store: keyof SparkOfflineDB, key: string): Promise<T | undefined> {
  const db = await openOfflineDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readonly");
    const req = tx.objectStore(store).get(key);
    req.onsuccess = () => resolve(req.result as T | undefined);
    req.onerror = () => reject(req.error);
  });
}

export async function idbGetAll<T>(store: keyof SparkOfflineDB): Promise<T[]> {
  const db = await openOfflineDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readonly");
    const req = tx.objectStore(store).getAll();
    req.onsuccess = () => resolve((req.result as T[]) ?? []);
    req.onerror = () => reject(req.error);
  });
}

export async function idbPut<T extends { [k: string]: unknown }>(
  store: keyof SparkOfflineDB,
  value: T
): Promise<void> {
  const db = await openOfflineDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readwrite");
    tx.objectStore(store).put(value);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function idbDelete(store: keyof SparkOfflineDB, key: string): Promise<void> {
  const db = await openOfflineDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readwrite");
    tx.objectStore(store).delete(key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function idbClearStore(store: keyof SparkOfflineDB): Promise<void> {
  const db = await openOfflineDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readwrite");
    tx.objectStore(store).clear();
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}
