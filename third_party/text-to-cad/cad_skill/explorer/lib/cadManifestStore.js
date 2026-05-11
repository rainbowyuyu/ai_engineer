import initialCadCatalog from "virtual:cad-catalog";

const DEFAULT_EXPLORER_ROOT_DIR = "";

function normalizeExplorerRootDir(value = DEFAULT_EXPLORER_ROOT_DIR) {
  const rawValue = String(value ?? "").trim();
  return rawValue.replace(/\\/g, "/").replace(/^\/+/, "").replace(/\/+$/, "");
}

function normalizeCadManifest(manifest, fallbackDir = DEFAULT_EXPLORER_ROOT_DIR) {
  if (!manifest || typeof manifest !== "object") {
    const normalizedFallbackDir = normalizeExplorerRootDir(fallbackDir);
    return {
      schemaVersion: 3,
      root: {
        dir: normalizedFallbackDir,
        name: normalizedFallbackDir.split("/").filter(Boolean).pop() || "",
        path: normalizedFallbackDir,
      },
      entries: [],
    };
  }

  const normalizedFallbackDir = normalizeExplorerRootDir(fallbackDir);
  return {
    ...manifest,
    root: manifest.root && typeof manifest.root === "object"
      ? manifest.root
      : {
          dir: normalizedFallbackDir,
          name: normalizedFallbackDir.split("/").filter(Boolean).pop() || "",
          path: normalizedFallbackDir,
        },
    entries: Array.isArray(manifest.entries) ? manifest.entries : [],
  };
}

const listeners = new Set();
/** 生产环境在拉取 /api/cad-explorer/catalog 完成前为 false，避免 ?file= 尚未进入清单时误报「File does not exist」。 */
const initialLiveReady = typeof import.meta !== "undefined" && import.meta.env && import.meta.env.DEV;
let currentSnapshot = {
  manifest: normalizeCadManifest(initialCadCatalog),
  revision: 0,
  liveCatalogReady: initialLiveReady,
};
let refreshRequestId = 0;

function publishCadManifest(nextManifest) {
  currentSnapshot = {
    manifest: normalizeCadManifest(nextManifest),
    revision: currentSnapshot.revision + 1,
    liveCatalogReady: true,
  };
  for (const listener of listeners) {
    listener();
  }
}

function finishLiveCatalogAttempt() {
  if (currentSnapshot.liveCatalogReady) {
    return;
  }
  currentSnapshot = {
    manifest: currentSnapshot.manifest,
    revision: currentSnapshot.revision + 1,
    liveCatalogReady: true,
  };
  for (const listener of listeners) {
    listener();
  }
}

async function refreshCadCatalog() {
  if (typeof window === "undefined" || !import.meta.env.DEV) {
    return;
  }
  const requestId = ++refreshRequestId;
  const response = await fetch("/__cad/catalog", {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to scan Explorer root: ${response.status} ${response.statusText}`);
  }
  const catalog = await response.json();
  if (requestId === refreshRequestId) {
    publishCadManifest(catalog);
  }
}

let _cachedExternalSnapshot = null;
let _cachedExternalKey = "";

export function getCadManifestSnapshot() {
  const key = `${currentSnapshot.revision}:${currentSnapshot.liveCatalogReady}`;
  if (_cachedExternalSnapshot && _cachedExternalKey === key) {
    return _cachedExternalSnapshot;
  }
  _cachedExternalKey = key;
  _cachedExternalSnapshot = {
    manifest: currentSnapshot.manifest,
    revision: currentSnapshot.revision,
    liveCatalogReady: currentSnapshot.liveCatalogReady,
  };
  return _cachedExternalSnapshot;
}

export function subscribeCadManifest(listener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

if (import.meta.hot) {
  import.meta.hot.accept("virtual:cad-catalog", (nextModule) => {
    publishCadManifest(nextModule?.default);
  });
  import.meta.hot.on("cad-catalog:changed", () => {
    refreshCadCatalog().catch((error) => {
      console.warn("Failed to refresh CAD catalog", error);
    });
  });
}

if (typeof window !== "undefined" && import.meta.env.DEV) {
  refreshCadCatalog().catch((error) => {
    console.warn("Failed to refresh CAD catalog", error);
  });
}

/**
 * 生产环境（如嵌入 beso_ai FastAPI）：构建时烘焙的 catalog 不包含之后生成的 STEP。
 * 宿主提供 GET /api/cad-explorer/catalog 时，启动后拉取一次以合并磁盘上的新文件。
 */
if (typeof window !== "undefined" && !import.meta.env.DEV) {
  const liveUrl = new URL("/api/cad-explorer/catalog", window.location.origin).toString();
  fetch(liveUrl, { cache: "no-store" })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return response.json();
    })
    .then((catalog) => {
      if (catalog && typeof catalog === "object") {
        publishCadManifest(catalog);
      } else {
        finishLiveCatalogAttempt();
      }
    })
    .catch((error) => {
      console.warn("Live CAD catalog fetch skipped (using baked manifest)", error);
      finishLiveCatalogAttempt();
    });
}
