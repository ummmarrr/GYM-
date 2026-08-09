/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute URL of the deployed API. Left unset locally so the Vite proxy handles /api. */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
