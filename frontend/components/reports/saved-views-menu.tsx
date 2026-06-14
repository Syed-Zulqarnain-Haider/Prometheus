"use client";

import { Bookmark, Trash2 } from "lucide-react";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useCreateView, useDeleteView, useSavedViews } from "@/lib/api-hooks";
import type { Filters } from "@/lib/filters";
import { useFilters } from "@/lib/use-filters";

/** Save the current filter/date/compare state as a named view and reload it.
 *  Views are per-user and scoped to the page they were saved from. */
export function SavedViewsMenu() {
  const pathname = usePathname();
  const { filters, setFilters } = useFilters();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");

  const { data: views } = useSavedViews();
  const createView = useCreateView();
  const deleteView = useDeleteView();

  const pageViews = (views ?? []).filter((v) => v.page === pathname);

  function save() {
    const trimmed = name.trim();
    if (!trimmed) return;
    createView.mutate(
      { name: trimmed, page: pathname, filters: filters as unknown as Record<string, unknown> },
      { onSuccess: () => setName("") },
    );
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2">
          <Bookmark className="h-4 w-4" />
          Views
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 space-y-3">
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Save current view</p>
          <div className="flex gap-2">
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="View name"
              className="h-8"
              onKeyDown={(event) => event.key === "Enter" && save()}
            />
            <Button size="sm" onClick={save} disabled={!name.trim() || createView.isPending}>
              Save
            </Button>
          </div>
        </div>

        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Saved on this page</p>
          {pageViews.length === 0 ? (
            <p className="text-xs text-muted-foreground">No saved views yet.</p>
          ) : (
            <ul className="space-y-1">
              {pageViews.map((view) => (
                <li key={view.id} className="flex items-center justify-between gap-2">
                  <button
                    type="button"
                    className="flex-1 truncate rounded px-2 py-1 text-left text-sm hover:bg-accent"
                    onClick={() => {
                      setFilters(view.filters as unknown as Filters);
                      setOpen(false);
                    }}
                  >
                    {view.name}
                  </button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 shrink-0"
                    onClick={() => deleteView.mutate(view.id)}
                    aria-label={`Delete ${view.name}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
