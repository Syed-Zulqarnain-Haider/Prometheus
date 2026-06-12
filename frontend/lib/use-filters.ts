"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

import { type Filters, filtersToParams, parseFilters } from "@/lib/filters";

/** Read + write the global filter state, fully synced to URL search params. */
export function useFilters(): {
  filters: Filters;
  setFilters: (next: Filters) => void;
} {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const filters = useMemo(
    () => parseFilters(new URLSearchParams(searchParams.toString())),
    [searchParams],
  );

  const setFilters = useCallback(
    (next: Filters) => {
      const params = filtersToParams(next);
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [router, pathname],
  );

  return { filters, setFilters };
}
