/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE: string;
  /** 构建时写入：`package.json` 版本 + git 短 SHA（或 local） */
  readonly VITE_APP_RELEASE: string;
  /** 页脚 / 关于页 GitHub 仓库链接 */
  readonly VITE_GITHUB_REPO_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
