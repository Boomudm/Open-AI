export type Paginated<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type PaginationParams = {
  page?: number;
  page_size?: number;
};

export const DEFAULT_PAGE_SIZE = 50;

export function paginationRange(page: number, pageSize: number, total: number) {
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  return { start, end };
}
