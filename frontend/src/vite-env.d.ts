/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_PREVIEW_INTERVAL_MS?: string;
  readonly VITE_COUNTS_INTERVAL_MS?: string;
  readonly VITE_PREVIEW_STAGGER_MS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
