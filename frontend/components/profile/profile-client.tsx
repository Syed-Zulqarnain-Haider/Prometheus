"use client";

import { format, parseISO } from "date-fns";
import { Camera, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  BG_CHANGE_EVENT,
  BG_EFFECT_KEY,
  BG_EFFECTS,
  BG_INTENSITY_KEY,
  readBgPreference,
} from "@/components/effects/background-fx";
import { ElasticSlider } from "@/components/effects/elastic-slider";
import { PersonAvatar } from "@/components/people/person-avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  useDeleteAvatar,
  useProfile,
  useUpdateProfile,
  useUploadAvatar,
} from "@/lib/people-hooks";

function stamp(iso: string | null): string {
  return iso ? format(parseISO(iso), "d MMM yyyy, HH:mm") : "Never";
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <Input
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

/** Your own profile: picture, name and details, plus the account's activity stamps.
 *  Email and roles are shown but not editable - identity and access are administered. */
export function ProfileClient() {
  const profile = useProfile();
  const update = useUpdateProfile();
  const upload = useUploadAvatar();
  const removeAvatar = useDeleteAvatar();
  const fileInput = useRef<HTMLInputElement>(null);

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [phone, setPhone] = useState("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Seed the form ONCE per account. Re-seeding on every refetch wiped in-progress typing
  // whenever anything invalidated the profile query (e.g. uploading an avatar).
  const data = profile.data;
  const seededFor = useRef<string | null>(null);
  useEffect(() => {
    if (!data || seededFor.current === data.user_id) return;
    seededFor.current = data.user_id;
    setFirstName(data.first_name ?? "");
    setLastName(data.last_name ?? "");
    setJobTitle(data.job_title ?? "");
    setPhone(data.phone ?? "");
  }, [data]);

  if (profile.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading your profile...</p>;
  }
  if (!data) {
    return <p className="text-sm text-destructive">Could not load your profile.</p>;
  }

  function save(): void {
    setError(null);
    setSaved(false);
    update.mutate(
      {
        first_name: firstName.trim() || null,
        last_name: lastName.trim() || null,
        job_title: jobTitle.trim() || null,
        phone: phone.trim() || null,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone ?? null,
      },
      {
        onSuccess: () => setSaved(true),
        onError: (err) => setError(err.message),
      },
    );
  }

  function pickFile(file: File | undefined): void {
    setError(null);
    if (!file) return;
    if (file.size > 512 * 1024) {
      setError("Images must be 512 KB or smaller.");
      return;
    }
    upload.mutate(file, { onError: (err) => setError(err.message) });
  }

  return (
    <div className="space-y-4">
    <div className="grid gap-4 lg:grid-cols-[20rem_1fr]">
      {/* ── Picture + account facts ─────────────────────────────── */}
      <Card>
        <CardContent className="flex flex-col items-center gap-3 pt-6 text-center">
          <PersonAvatar
            userId={data.user_id}
            displayName={data.display_name}
            email={data.email}
            hasAvatar={data.has_avatar}
            size={96}
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5"
              disabled={upload.isPending}
              onClick={() => fileInput.current?.click()}
            >
              <Camera className="h-3.5 w-3.5" />
              {data.has_avatar ? "Change photo" : "Upload photo"}
            </Button>
            {data.has_avatar && (
              <Button
                size="sm"
                variant="ghost"
                aria-label="Remove photo"
                disabled={removeAvatar.isPending}
                onClick={() => removeAvatar.mutate()}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
          <input
            ref={fileInput}
            type="file"
            accept="image/png,image/jpeg,image/gif,image/webp"
            className="hidden"
            onChange={(event) => pickFile(event.target.files?.[0])}
          />
          <p className="text-xs text-muted-foreground">PNG, JPEG, GIF or WEBP, up to 512 KB.</p>

          <div className="mt-2 w-full space-y-1.5 border-t pt-3 text-left text-sm">
            <p className="flex justify-between gap-2">
              <span className="text-muted-foreground">Email</span>
              <span className="truncate">{data.email}</span>
            </p>
            <p className="flex justify-between gap-2">
              <span className="text-muted-foreground">Roles</span>
              <span className="flex flex-wrap justify-end gap-1">
                {data.roles.map((role) => (
                  <Badge key={role} variant="secondary">
                    {role}
                  </Badge>
                ))}
              </span>
            </p>
            <p className="flex justify-between gap-2">
              <span className="text-muted-foreground">Last login</span>
              <span>{stamp(data.last_login_at)}</span>
            </p>
            <p className="flex justify-between gap-2">
              <span className="text-muted-foreground">Last active</span>
              <span>{stamp(data.last_seen_at)}</span>
            </p>
            <p className="flex justify-between gap-2">
              <span className="text-muted-foreground">Member since</span>
              <span>{stamp(data.created_at)}</span>
            </p>
          </div>
        </CardContent>
      </Card>

      {/* ── Editable details ────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold normal-case tracking-normal text-foreground">
            Your details
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="First name" value={firstName} onChange={setFirstName} placeholder="Zulqarnain" />
            <Field label="Last name" value={lastName} onChange={setLastName} placeholder="Haider" />
            <Field label="Job title" value={jobTitle} onChange={setJobTitle} placeholder="Head of Product" />
            <Field label="Phone" value={phone} onChange={setPhone} placeholder="+92 ..." />
          </div>
          <p className="text-xs text-muted-foreground">
            Your name is shown in chat, sharing and the audit trail. Email and roles are
            managed by an administrator.
          </p>
          <div className="flex items-center gap-3">
            <Button disabled={update.isPending} onClick={save}>
              {update.isPending ? "Saving..." : "Save changes"}
            </Button>
            {saved && !update.isPending && (
              <span className="text-sm text-[color:var(--color-positive)]">Saved.</span>
            )}
            {error && <span className="text-sm text-destructive">{error}</span>}
          </div>
        </CardContent>
      </Card>
    </div>

    {/* ── Appearance: the ambient background, chosen per taste (owner request). The
        preference is per-browser; the canvas honours reduced-motion and hidden tabs. */}
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-semibold normal-case tracking-normal text-foreground">
          Appearance
        </CardTitle>
      </CardHeader>
      <CardContent>
        <AppearancePicker />
      </CardContent>
    </Card>
    </div>
  );
}

function AppearancePicker() {
  const [effect, setEffect] = useState("none");
  const [intensity, setIntensity] = useState(0.5);
  useEffect(() => {
    const pref = readBgPreference();
    setEffect(pref.effect);
    setIntensity(pref.intensity);
  }, []);

  function apply(nextEffect: string, nextIntensity: number): void {
    setEffect(nextEffect);
    setIntensity(nextIntensity);
    try {
      localStorage.setItem(BG_EFFECT_KEY, nextEffect);
      localStorage.setItem(BG_INTENSITY_KEY, String(nextIntensity));
    } catch {
      /* storage blocked - applies for this session only */
    }
    window.dispatchEvent(new Event(BG_CHANGE_EVENT));
  }

  return (
    <div className="space-y-4">
      <div>
        <p className="mb-2 text-xs font-medium text-muted-foreground">Background effect</p>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
          {BG_EFFECTS.map((entry) => (
            <button
              key={entry.id}
              type="button"
              onClick={() => apply(entry.id, intensity)}
              className={cn(
                "rounded-[var(--radius-inner)] border px-2 py-2 text-[11px] transition-all duration-[var(--dur-fast)] hover:scale-[1.03]",
                effect === entry.id
                  ? "border-[color:var(--color-accent)] bg-[color:var(--color-accent-soft)] font-semibold"
                  : "text-muted-foreground hover:bg-accent",
              )}
            >
              {entry.label}
            </button>
          ))}
        </div>
      </div>
      <div className="max-w-xs">
        <ElasticSlider
          label="Effect intensity"
          value={intensity}
          onChange={(value) => apply(effect, value)}
        />
      </div>
      <p className="text-[11px] text-muted-foreground">
        Backgrounds pause in hidden tabs and switch off automatically for reduced-motion
        preferences. Intensity is capped so charts stay readable.
      </p>
    </div>
  );
}
