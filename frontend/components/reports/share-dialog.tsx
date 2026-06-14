"use client";

import { Share2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useDirectory, useShareReport } from "@/lib/api-hooks";

/** Share a report with another user. Non-admins create a PENDING request that an
 *  admin must approve; admins' shares are approved immediately. */
export function ShareDialog({ reportId }: { reportId: string }) {
  const [open, setOpen] = useState(false);
  const [recipient, setRecipient] = useState<string>("");
  const { data: directory } = useDirectory();
  const share = useShareReport();

  const people = directory ?? [];

  function submit() {
    if (!recipient) return;
    share.mutate({ reportId, sharedWith: recipient });
  }

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setRecipient("");
          share.reset();
        }
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2">
          <Share2 className="h-4 w-4" />
          Share
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 space-y-3">
        <p className="text-xs font-medium text-muted-foreground">
          Share with — recipients always view through their own access.
        </p>
        <Select value={recipient} onValueChange={setRecipient}>
          <SelectTrigger className="h-8">
            <SelectValue placeholder="Select a person" />
          </SelectTrigger>
          <SelectContent>
            {people.map((person) => (
              <SelectItem key={person.user_id} value={person.user_id}>
                {person.display_name ?? person.email}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button
          size="sm"
          className="w-full"
          onClick={submit}
          disabled={!recipient || share.isPending}
        >
          {share.isPending ? "Sharing…" : "Share report"}
        </Button>

        {share.isSuccess && (
          <p className="text-xs text-muted-foreground">
            {share.data.status === "approved"
              ? "Shared — the recipient can see it now."
              : "Request sent — awaiting admin approval."}
          </p>
        )}
        {share.isError && (
          <p className="text-xs text-destructive">
            {share.error instanceof Error ? share.error.message : "Could not share."}
          </p>
        )}
      </PopoverContent>
    </Popover>
  );
}
