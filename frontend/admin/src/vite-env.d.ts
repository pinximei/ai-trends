/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 构建时写入：`package.json` 版本 + git 短 SHA（或 local） */
  readonly VITE_APP_RELEASE: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
