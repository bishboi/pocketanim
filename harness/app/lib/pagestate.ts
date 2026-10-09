/**
 * A page's state kept in this browser (IndexedDB, which holds a lecture's versions and traces where localStorage's
 * few megabytes do not), so reloading the page brings it back as it was. Nothing here is required: without
 * storage (a private window), the page simply starts empty.
 */

const DB = "pocketanim";
const STORE = "pages";

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function loadPage<T>(key: string): Promise<T | null> {
  try {
    const db = await open();
    return await new Promise<T | null>((resolve) => {
      const request = db.transaction(STORE, "readonly").objectStore(STORE).get(key);
      request.onsuccess = () => resolve((request.result as T | undefined) ?? null);
      request.onerror = () => resolve(null);
    });
  } catch {
    return null;
  }
}

export async function savePage<T>(key: string, value: T): Promise<void> {
  try {
    const db = await open();
    await new Promise<void>((resolve) => {
      const tx = db.transaction(STORE, "readwrite");
      // Structured-cloned: functions and promises are left out by the caller, and JSON keeps it plain data.
      tx.objectStore(STORE).put(JSON.parse(JSON.stringify(value)), key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
      tx.onabort = () => resolve();
    });
  } catch {
    // not kept: the page still works
  }
}

export async function clearPage(key: string): Promise<void> {
  try {
    const db = await open();
    await new Promise<void>((resolve) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).delete(key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });
  } catch {
    // nothing to clear
  }
}
