/** 与预设模板同名的数据源标识；从 src/data/source-presets-fallback.json 派生（运行 backend/scripts/export_admin_source_presets_fallback.py 同步） */
import data from "./data/source-presets-fallback.json";

export const PRESET_TEMPLATE_SOURCE_SLUGS: ReadonlySet<string> = new Set(data.items.map((i) => i.source));
