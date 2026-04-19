/** 前台「板块」导航：最多 9 个主板块 +「其他」占位（合起来最多 10 个入口） */
export const MAX_PRIMARY_SEGMENT_CHIPS = 9;

export function splitPrimaryOverflow<T extends { id: number }>(all: T[]): { primary: T[]; overflow: T[] } {
  return {
    primary: all.slice(0, MAX_PRIMARY_SEGMENT_CHIPS),
    overflow: all.slice(MAX_PRIMARY_SEGMENT_CHIPS),
  };
}
