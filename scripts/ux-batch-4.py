#!/usr/bin/env python3
"""UX batch 4: the glossary rewritten, the sidebar order on your account, and an app
editor you can open without leaving the page you are on.

  A. GLOSSARY.  Rewritten from scratch, in ordinary English, covering every column the
     registry defines - what it counts, where it comes from, and how it is worked out.
     Search, section anchors, the five rules that decide what the numbers mean, and the
     quirks that look like bugs until somebody explains them (Apple lag, Unassigned,
     gross vs net, history moving when ownership changes). Shipped as whole files, so
     there is no anchor to miss; the OLD page is printed in full before it is replaced,
     so nothing in it is lost silently.

  B. SIDEBAR ORDER.  Wired to useNavOrder() from batch 2, so the arrangement lives on the
     account instead of in one browser profile. The localStorage load and save are
     removed structurally - the statements are matched on their CODE, not on the comments
     around them - and the section refuses to write anything if the file does not look
     the way it expects.

  C. EDIT AN APP WHERE YOU FOUND IT.  A drawer that edits App Master in place, mounted
     once in the shell and opened by ?edit-app=<key>, so a refresh keeps it open and a
     link opens straight onto it. Wired into the Apps Explorer row. Saving invalidates
     everything, because a pod change rewrites history everywhere.

  D. RECON of the Spotlight board, so its Edit button can be wired with certainty rather
     than guessed at.

Sections are independent: one that cannot match its anchors is skipped and reported
rather than taking the others down with it. Every section is idempotent.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
APP_LAYOUT = ROOT / "frontend/app/(app)/layout.tsx"
SIDEBAR = ROOT / "frontend/components/layout/sidebar.tsx"
EXPLORER = ROOT / "frontend/components/apps/apps-explorer.tsx"
NAV_ORDER_TS = ROOT / "frontend/lib/nav-order.ts"

# Generated asset bodies: (repo-relative path, file contents).

GLOSSARY_DATA = (
    "frontend/lib/glossary-data.ts",
    r"""/** One entry in the glossary. `name` is the column as it appears in exports and the API;
 *  `label` is what the dashboard calls it; `plain` is the definition in ordinary English. */
export interface Term {
  name: string;
  label: string;
  plain: string;
  formula?: string;
  note?: string;
}

export interface Section {
  id: string;
  title: string;
  blurb: string;
  terms: Term[];
}

/** The rules that decide what every number on the dashboard means. These are decisions,
 *  not conventions - they are applied the same way everywhere, including in exports. */
export const RULES: { title: string; body: string }[] = [
  {
    title: "Total revenue is purchases plus ads",
    body: "Total revenue = in-app purchase revenue after store fees and refunds, plus ad revenue. Nothing else is added to it, so it can always be split back into exactly those two parts.",
  },
  {
    title: "Ad revenue means AdMob and AppLovin only",
    body: "Mintegral money is deliberately left out. It is already included inside what AdMob reports through mediation, so counting it separately would count the same dollars twice. This is not an oversight, and it should not be fixed.",
  },
  {
    title: "Profit is revenue minus what it cost to get and run",
    body: "Profit = total revenue - user acquisition spend - tech cost. Salaries, office costs and anything else outside those two lines are not part of it.",
  },
  {
    title: "Ratios are calculated once, upstream",
    body: "ROAS, CPI, eCPM, click-through rate and organic share are worked out in the data warehouse before the dashboard sees them - not re-derived by each page. That is why the same ratio reads the same on every screen and in every export.",
  },
  {
    title: "You only ever see what you are allowed to see",
    body: "Filters and pages can narrow what you are looking at; they can never widen it. The rows and the columns you can reach are decided by the server from your account, so an export contains exactly what the screen could show you and nothing more.",
  },
];

export const SECTIONS: Section[] = [
  {
    id: "identity",
    title: "Identity and ownership",
    blurb:
      "How an app is identified, and who is accountable for it. These are the fields you group and filter by.",
    terms: [
      { name: "date", label: "Date", plain: "The day the activity happened, in UTC. Every row in the warehouse is one app, on one platform, on one day." },
      { name: "platform", label: "Platform", plain: "Either ios or android. An app that ships on both appears as two rows per day, and the totals add them together." },
      { name: "app_name", label: "App", plain: "The store name of the app." },
      { name: "canonical_key", label: "Canonical key", plain: "The single identifier that ties the iOS and Android versions of the same app together, so a cross-platform app rolls up as one product." },
      { name: "apple_id", label: "Apple ID", plain: "Apple numeric identifier for the app. iOS rows are keyed on this." },
      { name: "ios_bundle_id", label: "iOS bundle ID", plain: "Reverse-domain identifier Apple uses for the build, for example com.example.game." },
      { name: "android_package", label: "Android package", plain: "Google Play package name. Android rows are keyed on this." },
      { name: "publisher", label: "Publisher", plain: "The store account the app is published under." },
      { name: "developer", label: "Developer", plain: "The developer name shown on the store listing. Often the same as the publisher, but not always." },
      { name: "pod", label: "Pod", plain: "The team that owns the app.", note: "An app with no team assigned yet shows as Unassigned rather than as a number." },
      { name: "pod_owner", label: "Pod owner", plain: "The person accountable for that team. Change it in App Master and the whole history moves with it, so past months are re-attributed too, not just today." },
      { name: "hou", label: "HoU", plain: "Head of Unit - the level above pod. Several pods roll up into one HoU." },
      { name: "app_category", label: "Category", plain: "The store category the app sits in, for example Puzzle or Finance." },
      { name: "ownership_type", label: "Ownership", plain: "Whether the app is fully ours or run with a partner." },
      { name: "is_mapped", label: "Mapped", plain: "Whether the app has been matched to an entry in App Master. Anything unmapped still has real numbers, but no pod, owner or HoU - the Data Health page lists them so they can be claimed." },
    ],
  },
  {
    id: "installs",
    title: "Installs from the stores",
    blurb:
      "What Apple and Google themselves report. These are store-reported counts, which is why they can differ from what an ad network claims.",
    terms: [
      { name: "store_first_time_installs", label: "First-time installs", plain: "People installing the app for the first time on that account. The closest thing to a genuinely new user." },
      { name: "store_redownloads", label: "Redownloads", plain: "Someone installing again on an account that had the app before - a new device, or a reinstall. Not a new user." },
      { name: "store_total_installs", label: "Total installs", plain: "First-time installs plus redownloads - every install the store recorded.", formula: "first-time installs + redownloads" },
      { name: "store_organic_installs", label: "Organic installs", plain: "Installs the store did not attribute to a paid campaign. People who found the app on their own." },
      { name: "organic_install_share", label: "Organic share", plain: "The share of installs that came in without being paid for. A high share means the app is being found rather than bought.", formula: "organic installs / total installs" },
      { name: "gp_uninstalls", label: "Uninstalls (Play)", plain: "Uninstalls reported by Google Play. Android only - Apple does not report this.", note: "Shown as a raw count on purpose. An uninstall rate is not published here, because the installs it would be divided by are counted on a different basis and the resulting percentage would look precise while being wrong." },
      { name: "apple_restores", label: "Restores (Apple)", plain: "Apple restoring a previous purchase or download to a device. Not a new install." },
    ],
  },
  {
    id: "ua",
    title: "User acquisition",
    blurb:
      "What was spent buying installs, and what that spend bought. Reported per network, then totalled.",
    terms: [
      { name: "total_ua_spend_usd", label: "UA spend", plain: "Everything spent on paid user acquisition, across all networks, in US dollars.", formula: "Facebook + Google Ads + Mintegral spend" },
      { name: "total_paid_installs", label: "Paid installs", plain: "Installs the networks claim they delivered, added up across networks." },
      { name: "cpi", label: "CPI", plain: "Cost per install - the average price paid for one install across all networks.", formula: "UA spend / paid installs" },
      { name: "fb_spend_usd", label: "Facebook spend", plain: "Spend on Meta or Facebook campaigns." },
      { name: "fb_paid_installs", label: "Facebook installs", plain: "Installs Meta attributes to its own campaigns." },
      { name: "fb_cpi", label: "Facebook CPI", plain: "Average cost of one install bought through Meta.", formula: "Facebook spend / Facebook installs" },
      { name: "fb_impressions", label: "Facebook impressions", plain: "Times a Meta ad was shown." },
      { name: "fb_clicks", label: "Facebook clicks", plain: "Times a Meta ad was clicked." },
      { name: "fb_ctr", label: "Facebook CTR", plain: "Share of Meta impressions that turned into a click.", formula: "clicks / impressions" },
      { name: "fb_purchases", label: "Facebook purchases", plain: "Purchases Meta attributes to its campaigns." },
      { name: "fb_purchase_value", label: "Facebook purchase value", plain: "Value of those purchases as reported by Meta. This is the network view, not accounting revenue - use IAP net for money actually received." },
      { name: "gads_spend_usd", label: "Google Ads spend", plain: "Spend on Google Ads campaigns." },
      { name: "gads_paid_installs", label: "Google Ads installs", plain: "Installs Google Ads attributes to its own campaigns." },
      { name: "gads_cpi", label: "Google Ads CPI", plain: "Average cost of one install bought through Google Ads.", formula: "Google Ads spend / Google Ads installs" },
      { name: "gads_impressions", label: "Google Ads impressions", plain: "Times a Google ad was shown." },
      { name: "gads_clicks", label: "Google Ads clicks", plain: "Times a Google ad was clicked." },
      { name: "gads_ctr", label: "Google Ads CTR", plain: "Share of Google impressions that turned into a click.", formula: "clicks / impressions" },
      { name: "gads_conversions", label: "Google Ads conversions", plain: "Conversions Google counts - the definition depends on how the campaign was set up, so treat it as a campaign signal rather than a revenue figure." },
      { name: "gads_conversions_value", label: "Google Ads conversion value", plain: "Value Google assigns to those conversions." },
      { name: "mint_adv_spend_usd", label: "Mintegral spend", plain: "Spend on Mintegral as an advertising network - money going out to buy installs.", note: "Not to be confused with Mintegral as a publisher, which is money coming in and is deliberately excluded from ad revenue." },
      { name: "mint_adv_paid_installs", label: "Mintegral installs", plain: "Installs Mintegral attributes to its campaigns." },
      { name: "mint_adv_cpi", label: "Mintegral CPI", plain: "Average cost of one install bought through Mintegral.", formula: "Mintegral spend / Mintegral installs" },
      { name: "mint_adv_impressions", label: "Mintegral impressions", plain: "Times a Mintegral ad was shown." },
      { name: "mint_adv_clicks", label: "Mintegral clicks", plain: "Times a Mintegral ad was clicked." },
      { name: "mint_adv_ctr", label: "Mintegral CTR", plain: "Share of Mintegral impressions that turned into a click.", formula: "clicks / impressions" },
    ],
  },
  {
    id: "ads",
    title: "Ad revenue",
    blurb:
      "Money earned from showing ads inside our own apps. AdMob and AppLovin only - see the rules above for why Mintegral is not here.",
    terms: [
      { name: "total_ad_revenue_usd", label: "Ad revenue", plain: "All money earned from in-app advertising.", formula: "AdMob + AppLovin" },
      { name: "admob_revenue_usd", label: "AdMob revenue", plain: "Ad money earned through AdMob, including everything AdMob mediates on our behalf." },
      { name: "admob_impressions", label: "AdMob impressions", plain: "Ads served through AdMob." },
      { name: "admob_ecpm", label: "AdMob eCPM", plain: "What a thousand AdMob ad views are worth. The usual way to compare how well ad inventory is paying.", formula: "AdMob revenue / impressions x 1000" },
      { name: "applovin_revenue_usd", label: "AppLovin revenue", plain: "Ad money earned through AppLovin." },
      { name: "applovin_impressions", label: "AppLovin impressions", plain: "Ads served through AppLovin." },
      { name: "applovin_ecpm", label: "AppLovin eCPM", plain: "What a thousand AppLovin ad views are worth.", formula: "AppLovin revenue / impressions x 1000" },
    ],
  },
  {
    id: "iap",
    title: "In-app purchases",
    blurb:
      "Money users pay inside the app. Gross is what they were charged; net is what actually reaches us after the store takes its cut and refunds are returned.",
    terms: [
      { name: "total_iap_net_usd", label: "IAP net", plain: "Purchase money we actually keep, across both stores, after store fees and refunds. This is the figure that feeds total revenue.", formula: "Google Play net + Apple net" },
      { name: "total_iap_gross_usd", label: "IAP gross", plain: "What users were charged in total, before fees and refunds. Always larger than net." },
      { name: "gp_iap_gross_usd", label: "Play gross", plain: "What users were charged on Google Play." },
      { name: "gp_iap_refunds_usd", label: "Play refunds", plain: "Money given back to users on Google Play." },
      { name: "gp_google_fee_usd", label: "Play fee", plain: "Google commission on those purchases." },
      { name: "gp_iap_net_usd", label: "Play net", plain: "What we keep from Google Play.", formula: "gross - refunds - fee" },
      { name: "gp_revenue_status", label: "Play status", plain: "Whether Google has finalised the figures for that day or is still reporting estimates." },
      { name: "apple_iap_gross_usd", label: "Apple gross", plain: "What users were charged on the App Store." },
      { name: "apple_iap_refunds_usd", label: "Apple refunds", plain: "Money given back to users on the App Store." },
      { name: "apple_fee_usd", label: "Apple fee", plain: "Apple commission on those purchases." },
      { name: "apple_iap_net_usd", label: "Apple net", plain: "What we keep from the App Store.", formula: "gross - refunds - fee" },
      { name: "apple_iap_purchases", label: "Apple purchases", plain: "Number of purchases on the App Store." },
      { name: "apple_revenue_status", label: "Apple status", plain: "Whether Apple has finalised the figures for that day or is still reporting estimates." },
    ],
  },
  {
    id: "profit",
    title: "Revenue and profit",
    blurb: "The headline numbers, and how each one is built from the parts above.",
    terms: [
      { name: "total_revenue_usd", label: "Total revenue", plain: "Everything earned - purchases we keep, plus ad money.", formula: "IAP net + ad revenue" },
      { name: "tech_cost_usd", label: "Tech cost", plain: "What it costs to run the app - servers, third-party services and similar. Not marketing, and not people." },
      { name: "profit_usd", label: "TF profit", plain: "What is left after paying to acquire users and to run the app.", formula: "total revenue - UA spend - tech cost" },
      { name: "roas", label: "ROAS", plain: "Return on ad spend. How many dollars of revenue each dollar of UA spend brought back. Above 1 means the spend paid for itself.", formula: "total revenue / UA spend" },
      { name: "ad_roas", label: "Ad ROAS", plain: "The same comparison using only ad revenue - useful for apps that monetise mostly through advertising.", formula: "ad revenue / UA spend" },
    ],
  },
  {
    id: "attribution",
    title: "Attribution (Adjust)",
    blurb:
      "Adjust numbers are synced and available as optional columns, but they do not drive any dashboard page. Where Adjust and the stores disagree, the stores are treated as the record.",
    terms: [
      { name: "adjust_installs", label: "Adjust installs", plain: "Installs Adjust recorded." },
      { name: "adjust_paid_installs", label: "Adjust paid installs", plain: "Installs Adjust attributed to a paid campaign." },
      { name: "adjust_organic_installs", label: "Adjust organic installs", plain: "Installs Adjust could not attribute to a campaign." },
      { name: "adjust_attribution", label: "Adjust attributions", plain: "Installs Adjust matched to a specific source." },
      { name: "adjust_conversions", label: "Adjust conversions", plain: "Conversion events Adjust recorded." },
      { name: "adjust_reattributions", label: "Adjust reattributions", plain: "Returning users Adjust credited to a campaign again." },
    ],
  },
];

/** Things that will look like bugs until you know about them. */
export const QUIRKS: { title: string; body: string }[] = [
  {
    title: "Apple data arrives two to three days late",
    body: "Recent iOS rows are often partial or zero until Apple catches up. Every page carries a data as of banner for exactly this reason - read it before treating a low recent number as a real drop.",
  },
  {
    title: "A zero today is usually not a zero",
    body: "For the current day and the one before it, an empty figure almost always means the source has not reported yet, not that nothing happened.",
  },
  {
    title: "Unassigned is a real group",
    body: "Apps that have not been given a pod yet are grouped as Unassigned rather than hidden. New apps land there automatically when they first appear in the data, so it is worth checking.",
  },
  {
    title: "Changing ownership rewrites history",
    body: "Move an app to a different pod, owner or HoU in App Master and every past day moves with it. Last month recalculates too. This is deliberate - it means a team page always reflects the apps that team owns today.",
  },
  {
    title: "Gross and net are not interchangeable",
    body: "Purchase figures come in two flavours. Gross is what users paid; net is what survives store fees and refunds. Revenue and profit always use net.",
  },
];
""",
)

GLOSSARY_CLIENT = (
    "frontend/components/glossary/glossary-client.tsx",
    r""""use client";

import { useMemo, useState } from "react";

import { QUIRKS, RULES, SECTIONS, type Section, type Term } from "@/lib/glossary-data";

/* The glossary. Written to be read by somebody who has just been handed the dashboard,
 * not by somebody who already knows what the columns mean.
 *
 * Deliberately dependency-free beyond React and the data module: it is the one page that
 * has to keep working while everything around it is being changed, and it is also the
 * page most likely to be read on a phone by somebody in a meeting. */

function matches(term: Term, needle: string): boolean {
  if (!needle) return true;
  const haystack = `${term.label} ${term.name} ${term.plain} ${term.formula ?? ""} ${
    term.note ?? ""
  }`.toLowerCase();
  return haystack.includes(needle);
}

function TermRow({ term }: { term: Term }) {
  return (
    <div className="border-t py-4 first:border-t-0 sm:grid sm:grid-cols-[minmax(0,14rem)_1fr] sm:gap-6">
      <div className="sm:pt-0.5">
        <div className="font-medium">{term.label}</div>
        <code className="mt-0.5 block break-all font-mono text-xs text-muted-foreground">
          {term.name}
        </code>
      </div>
      <div className="mt-1 sm:mt-0">
        <p className="text-sm leading-relaxed">{term.plain}</p>
        {term.formula ? (
          <p className="mt-2 inline-block rounded bg-muted px-2 py-1 font-mono text-xs text-muted-foreground">
            {term.formula}
          </p>
        ) : null}
        {term.note ? (
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{term.note}</p>
        ) : null}
      </div>
    </div>
  );
}

function SectionBlock({ section, needle }: { section: Section; needle: string }) {
  const terms = section.terms.filter((t) => matches(t, needle));
  if (terms.length === 0) return null;
  return (
    <section id={section.id} className="scroll-mt-24">
      <h2 className="text-lg font-semibold tracking-tight">{section.title}</h2>
      <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{section.blurb}</p>
      <div className="mt-4 rounded-lg border bg-card px-4 sm:px-6">
        {terms.map((term) => (
          <TermRow key={term.name} term={term} />
        ))}
      </div>
    </section>
  );
}

export function GlossaryClient() {
  const [search, setSearch] = useState("");
  const needle = search.trim().toLowerCase();

  const hits = useMemo(
    () => SECTIONS.reduce((n, s) => n + s.terms.filter((t) => matches(t, needle)).length, 0),
    [needle],
  );
  const total = useMemo(() => SECTIONS.reduce((n, s) => n + s.terms.length, 0), []);

  return (
    <div className="space-y-8 pb-12">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Glossary</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
          Every figure on this dashboard, in plain language: what it counts, where it comes
          from, and how it is worked out. {total} terms.
        </p>
      </div>

      <div className="sticky top-0 z-10 -mx-4 bg-background/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search for a term, a column name, or a word in a definition"
          aria-label="Search the glossary"
          className="w-full rounded-md border bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-[color:var(--color-accent)]"
        />
        {needle ? (
          <p className="mt-2 text-xs text-muted-foreground">
            {hits} of {total} terms match.
          </p>
        ) : (
          <nav className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {SECTIONS.map((s) => (
              <a key={s.id} href={`#${s.id}`} className="hover:text-foreground hover:underline">
                {s.title}
              </a>
            ))}
            <a href="#quirks" className="hover:text-foreground hover:underline">
              Things worth knowing
            </a>
          </nav>
        )}
      </div>

      {needle ? null : (
        <section className="rounded-lg border bg-card p-4 sm:p-6">
          <h2 className="text-lg font-semibold tracking-tight">How the numbers fit together</h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Five decisions that apply everywhere - on every page, in every export, for
            everyone.
          </p>
          <dl className="mt-4 space-y-4">
            {RULES.map((rule) => (
              <div key={rule.title}>
                <dt className="text-sm font-medium">{rule.title}</dt>
                <dd className="mt-0.5 max-w-3xl text-sm leading-relaxed text-muted-foreground">
                  {rule.body}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {SECTIONS.map((section) => (
        <SectionBlock key={section.id} section={section} needle={needle} />
      ))}

      {hits === 0 ? (
        <p className="text-sm text-muted-foreground">
          Nothing matches that. Try a shorter word, or the column name as it appears in an
          export.
        </p>
      ) : null}

      {needle ? null : (
        <section id="quirks" className="scroll-mt-24">
          <h2 className="text-lg font-semibold tracking-tight">Things worth knowing</h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Behaviour that looks like a bug until somebody explains it.
          </p>
          <dl className="mt-4 space-y-4 rounded-lg border bg-card p-4 sm:p-6">
            {QUIRKS.map((quirk) => (
              <div key={quirk.title}>
                <dt className="text-sm font-medium">{quirk.title}</dt>
                <dd className="mt-0.5 max-w-3xl text-sm leading-relaxed text-muted-foreground">
                  {quirk.body}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}
    </div>
  );
}
""",
)

GLOSSARY_PAGE = (
    "frontend/app/(app)/glossary/page.tsx",
    r"""import { GlossaryClient } from "@/components/glossary/glossary-client";

export const metadata = { title: "Glossary" };

export default function GlossaryPage() {
  return <GlossaryClient />;
}
""",
)

EDIT_DRAWER = (
    "frontend/components/apps/app-edit-drawer.tsx",
    r""""use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { apiFetch } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { invalidateAfterAttributionChange } from "@/lib/invalidate";

/* Edit an app in place, from wherever you happen to be looking at it.
 *
 * Being sent to App Master to change one field means losing the page you were on, the
 * filters you had set and your place in a long table, to make an edit you could have
 * described in four words. This is the same edit, in a drawer, over the top of whatever
 * you were doing.
 *
 * Deliberately self-contained: it talks to the App Master endpoints directly rather than
 * through the shared hook file, so it does not inherit that module's filter shape and
 * cannot be broken by a field being added to it. The RULES are all server-side anyway -
 * which columns are editable, and whether this caller may edit them at all, is decided by
 * the API, not here. */

interface ColumnMeta {
  name: string;
  type: "text" | "bigint" | "boolean" | "double" | "timestamptz";
  editable: boolean;
}

interface ListResponse {
  rows: Record<string, unknown>[];
  columns: ColumnMeta[];
  primary_key: string;
}

/** Fields nobody should be re-typing by hand: identifiers the pipeline matches on, and
 *  bookkeeping the sync writes. The server has the final say; this only keeps the form
 *  short and the mistakes fewer. */
const HIDDEN = /(^id$|_at$|^last_synced|^created|^updated)/;

function label(name: string): string {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function asFormValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

/** Turn a form string back into what the API expects, or undefined if it is unusable. */
function parse(raw: string, type: ColumnMeta["type"]): unknown {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  if (type === "boolean") return trimmed === "true";
  if (type === "bigint" || type === "double") {
    const n = Number(trimmed);
    return Number.isFinite(n) ? n : undefined;
  }
  return trimmed;
}

export function AppEditDrawer({ appKey, onClose }: { appKey: string; onClose: () => void }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  // The list endpoint is the only reader we are sure exists, so the row is fetched by
  // searching for its own key and then matched exactly - a search that returns something
  // similar is not the same app, and editing the wrong app silently would be far worse
  // than saying we could not find it.
  const query = useQuery({
    queryKey: ["app-master", { search: appKey, limit: 50, offset: 0 }],
    queryFn: () =>
      apiFetch<ListResponse>(
        `/api/v1/app-master?search=${encodeURIComponent(appKey)}&limit=50&offset=0`,
      ),
    enabled: Boolean(user) && appKey.length > 0,
  });

  const primaryKey = query.data?.primary_key ?? "";
  const row = useMemo(() => {
    if (!query.data) return null;
    return (
      query.data.rows.find((r) => String(r[query.data.primary_key] ?? "") === appKey) ?? null
    );
  }, [query.data, appKey]);

  const editable = useMemo(
    () =>
      (query.data?.columns ?? []).filter(
        (c) => c.editable && c.name !== primaryKey && !HIDDEN.test(c.name),
      ),
    [query.data, primaryKey],
  );

  // Reseed the form whenever a different app is opened, so the drawer never shows one
  // app's name over another app's numbers.
  useEffect(() => {
    if (!row) return;
    const next: Record<string, string> = {};
    for (const column of editable) next[column.name] = asFormValue(row[column.name]);
    setDraft(next);
    setError(null);
  }, [row, editable]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch<Record<string, unknown>>(`/api/v1/app-master/${encodeURIComponent(appKey)}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      // A pod or HoU change rewrites history everywhere, so nothing cached is safe.
      invalidateAfterAttributionChange(queryClient);
      onClose();
    },
    onError: (err: unknown) => setError(err instanceof Error ? err.message : "Save failed"),
  });

  function submit() {
    if (!row) return;
    const body: Record<string, unknown> = {};
    for (const column of editable) {
      const raw = draft[column.name] ?? "";
      if (raw === asFormValue(row[column.name])) continue; // unchanged - do not send it
      const value = parse(raw, column.type);
      if (value === undefined) {
        setError(`${label(column.name)} is not a valid number.`);
        return;
      }
      body[column.name] = value;
    }
    if (Object.keys(body).length === 0) {
      onClose(); // nothing changed; closing is the honest outcome, not a fake save
      return;
    }
    setError(null);
    save.mutate(body);
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <button
        type="button"
        aria-label="Close"
        className="absolute inset-0 h-full w-full cursor-default bg-black/40"
        onClick={onClose}
      />
      <div className="relative flex h-full w-full max-w-md flex-col border-l bg-card shadow-xl">
        <div className="flex items-start justify-between gap-4 border-b px-5 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold">
              {String(row?.app_name ?? "Edit app")}
            </h2>
            <code className="mt-0.5 block truncate font-mono text-xs text-muted-foreground">
              {appKey}
            </code>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded px-2 py-1 text-sm text-muted-foreground hover:text-foreground"
          >
            Close
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {query.isLoading ? <p className="text-sm text-muted-foreground">Loading…</p> : null}
          {query.isError ? (
            <p className="text-sm text-destructive">
              Could not load this app. You may not have access to it.
            </p>
          ) : null}
          {query.isSuccess && !row ? (
            <p className="text-sm text-muted-foreground">
              No App Master entry matches this app yet. It will appear here once the next
              sync maps it.
            </p>
          ) : null}

          {row ? (
            <div className="space-y-4">
              {editable.map((column) => (
                <label key={column.name} className="block">
                  <span className="text-sm font-medium">{label(column.name)}</span>
                  {column.type === "boolean" ? (
                    <select
                      value={draft[column.name] ?? ""}
                      onChange={(e) =>
                        setDraft((d) => ({ ...d, [column.name]: e.target.value }))
                      }
                      className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                    >
                      <option value="">Not set</option>
                      <option value="true">Yes</option>
                      <option value="false">No</option>
                    </select>
                  ) : (
                    <input
                      value={draft[column.name] ?? ""}
                      inputMode={
                        column.type === "bigint" || column.type === "double"
                          ? "numeric"
                          : undefined
                      }
                      onChange={(e) =>
                        setDraft((d) => ({ ...d, [column.name]: e.target.value }))
                      }
                      className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                    />
                  )}
                </label>
              ))}
              {editable.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Nothing on this app is editable with your permissions.
                </p>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="border-t px-5 py-4">
          {error ? <p className="mb-3 text-sm text-destructive">{error}</p> : null}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border px-3 py-2 text-sm hover:bg-muted"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={!row || save.isPending || editable.length === 0}
              className="rounded-md bg-[color:var(--color-accent)] px-3 py-2 text-sm font-medium text-black disabled:opacity-50"
            >
              {save.isPending ? "Saving…" : "Save changes"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
""",
)

EDIT_PORTAL = (
    "frontend/components/apps/app-edit-portal.tsx",
    r""""use client";

import { useCallback, useEffect, useState } from "react";

import { AppEditDrawer } from "@/components/apps/app-edit-drawer";

/* One app editor, mounted once for the whole app, opened by URL.
 *
 * Keeping it in the shell rather than inside each table means any screen can offer
 * "edit this app" without rebuilding the form, and - because the app being edited lives
 * in the query string - the drawer survives a refresh and a shared link opens straight
 * onto it.
 *
 * The URL is read from window.location rather than useSearchParams on purpose: the hook
 * would pull every page that renders this into a build-time Suspense boundary, and
 * reading the URL during render would make the server and first client render disagree. */

const PARAM = "edit-app";
const EVENT = "prometheus:edit-app";

function keyFromUrl(): string | null {
  const value = new URLSearchParams(window.location.search).get(PARAM);
  return value && value.length > 0 ? value : null;
}

/** Open the editor for an app from anywhere, without importing the drawer itself. */
export function openAppEditor(appKey: string): void {
  const url = new URL(window.location.href);
  url.searchParams.set(PARAM, appKey);
  window.history.pushState(null, "", url.toString());
  window.dispatchEvent(new Event(EVENT));
}

export function AppEditPortal() {
  const [appKey, setAppKey] = useState<string | null>(null);

  useEffect(() => {
    const sync = () => setAppKey(keyFromUrl());
    sync();
    window.addEventListener(EVENT, sync);
    // popstate covers the back button: closing the drawer by navigating back should
    // actually close it, not leave it floating over the previous page.
    window.addEventListener("popstate", sync);
    return () => {
      window.removeEventListener(EVENT, sync);
      window.removeEventListener("popstate", sync);
    };
  }, []);

  const close = useCallback(() => {
    setAppKey(null);
    const url = new URL(window.location.href);
    url.searchParams.delete(PARAM);
    window.history.replaceState(null, "", url.toString());
  }, []);

  if (!appKey) return null;
  return <AppEditDrawer appKey={appKey} onClose={close} />;
}
""",
)

skipped: list[str] = []
notes: list[str] = []


class Section:
    """One independent unit of work. Its writes land only if it finishes cleanly."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.writes: dict[Path, str] = {}
        self.reasons: list[str] = []
        self.done: list[str] = []

    def skip(self, reason: str, region: str = "") -> None:
        self.reasons.append(reason + (f"\n{indent(region)}" if region else ""))

    def commit(self) -> None:
        if self.reasons:
            skipped.append(
                f"[{self.name}] SKIPPED - nothing from this section was written:\n"
                + "\n".join(f"  * {r}" for r in self.reasons)
            )
            return
        for path, text in self.writes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        for line in self.done or ["already applied - left alone"]:
            notes.append(f"[{self.name}] {line}")


def indent(text: str) -> str:
    return "\n".join(f"      | {line}" for line in text.rstrip("\n").splitlines())


def window(text: str, needle: str, before: int = 4, after: int = 14) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            return "\n".join(lines[max(0, i - before) : i + after])
    return "(not found anywhere in the file)"


def add_import(text: str, statement: str) -> str:
    if statement in text:
        return text
    imports = list(re.finditer(r"^import [^\n]*;$", text, re.M))
    if not imports:
        return statement + "\n" + text
    end = imports[-1].end()
    return text[:end] + "\n" + statement + text[end:]


# ─────────────────────────────────────────────────────────────────────────────
# A. The glossary, rewritten
# ─────────────────────────────────────────────────────────────────────────────


def section_glossary() -> Section:
    section = Section("glossary")
    for rel, body in (GLOSSARY_DATA, GLOSSARY_CLIENT, GLOSSARY_PAGE):
        path = ROOT / rel
        if path.exists() and path.read_text() == body:
            continue
        if path.exists():
            print(f"\n### REPLACED: {rel} - the version being replaced, in full:")
            for i, line in enumerate(path.read_text().splitlines(), 1):
                print(f"  {i:>4}  {line}")
        section.writes[path] = body
        section.done.append(f"{rel} written")
    return section


# ─────────────────────────────────────────────────────────────────────────────
# B. Sidebar order -> the account
# ─────────────────────────────────────────────────────────────────────────────

# Every one of these matches CODE, never a comment or a piece of prose - the point is
# that rewording a comment upstream must not change whether this patch applies.
ORDER_STATE_RE = re.compile(
    r"const \[order, setOrder\] = useState<string\[\]>\(\s*\[\]\s*\);"
)
LOAD_EFFECT_RE = re.compile(
    r"\n[ \t]*useEffect\(\(\) => \{\s*if \(!orderKey\) return;\s*try \{[^{}]*\}"
    r"\s*catch\s*(?:\([^)]*\))?\s*\{[^{}]*\}\s*\}, \[orderKey\]\);"
)
SAVE_BLOCK_RE = re.compile(
    r"\n[ \t]*if \(!orderKey\) return;\s*try \{[^{}]*\}\s*catch\s*(?:\([^)]*\))?\s*\{[^{}]*\}"
)
ORDER_KEY_CONST_RE = re.compile(
    r"\n(?:[ \t]*//[^\n]*\n)*[ \t]*const orderKey = [^\n;]*;"
)
ORDER_KEY_DECL_RE = re.compile(r'\nconst ORDER_KEY = "[^"]*";')
NAV_ORDER_IMPORT = 'import { useNavOrder } from "@/lib/nav-order";'


def section_sidebar_order() -> Section:
    section = Section("sidebar-order")
    if not SIDEBAR.exists():
        section.skip(f"missing {SIDEBAR}")
        return section
    if not NAV_ORDER_TS.exists():
        section.skip(
            f"{NAV_ORDER_TS} is not there yet - run ux-batch-2.py first, which creates it"
        )
        return section

    text = SIDEBAR.read_text()
    if "useNavOrder(" in text:
        return section

    if len(ORDER_STATE_RE.findall(text)) != 1:
        section.skip(
            "expected exactly one `const [order, setOrder] = useState<string[]>([])`",
            window(text, "setOrder"),
        )
        return section

    steps: list[tuple[str, re.Pattern[str]]] = [
        ("the localStorage load effect", LOAD_EFFECT_RE),
        ("the localStorage save inside move()", SAVE_BLOCK_RE),
        ("the per-user orderKey constant", ORDER_KEY_CONST_RE),
    ]
    for label, pattern in steps:
        hits = pattern.findall(text)
        if len(hits) != 1:
            section.skip(
                f"expected exactly one occurrence of {label}, found {len(hits)}",
                window(text, "orderKey"),
            )
            return section
        text = pattern.sub("", text, count=1)

    text = ORDER_STATE_RE.sub(
        "const { order, setOrder } = useNavOrder(me?.user_id ?? null);", text, count=1
    )

    # Only drop the base key once nothing refers to it. If something still does, leaving
    # it is harmless; removing it would not be.
    if text.count("ORDER_KEY") == 1:
        text = ORDER_KEY_DECL_RE.sub("", text, count=1)

    leftover = [
        name for name in ("orderKey", "localStorage.getItem(orderKey)") if name in text
    ]
    if leftover:
        section.skip(
            f"references to {leftover} survived the rewrite - refusing to leave the file "
            "half-converted",
            window(text, "orderKey"),
        )
        return section
    if "useState" not in text:
        section.skip(
            "that was the file's only useState - the React import would dangle"
        )
        return section

    # Removing whole statements leaves the gaps they used to fill.
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = add_import(text, NAV_ORDER_IMPORT)
    section.writes[SIDEBAR] = text
    section.done.append("nav order now saved to the account, not to one browser")
    return section


# ─────────────────────────────────────────────────────────────────────────────
# C. Edit an app without leaving the page
# ─────────────────────────────────────────────────────────────────────────────

CHILDREN_RE = re.compile(r"\{children\}")
PORTAL_IMPORT = 'import { AppEditPortal } from "@/components/apps/app-edit-portal";'
EDITOR_IMPORT = 'import { openAppEditor } from "@/components/apps/app-edit-portal";'
STORE_ICON_RE = re.compile(r"[ \t]*<StoreLinkIcon\b[^>]*/>")

EDIT_BUTTON = """
            <button
              type="button"
              title="Edit this app"
              aria-label="Edit this app"
              onClick={(event) => {
                // The row itself navigates to the app page; editing must not do both.
                event.stopPropagation();
                openAppEditor(
                  String(
                    row.original.app_key ??
                      row.original.canonical_key ??
                      row.original.android_package ??
                      row.original.apple_id ??
                      "",
                  ),
                );
              }}
              className="rounded px-1 text-xs text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100 focus:opacity-100"
            >
              Edit
            </button>"""


def section_app_editor() -> Section:
    section = Section("app-editor")
    for rel, body in (EDIT_DRAWER, EDIT_PORTAL):
        path = ROOT / rel
        if not path.exists() or path.read_text() != body:
            section.writes[path] = body
            section.done.append(f"{rel} written")

    if not (ROOT / "frontend/lib/invalidate.ts").exists():
        section.skip(
            "frontend/lib/invalidate.ts is not there yet - run ux-batch-3.py first, "
            "which creates it"
        )
        return section

    # Mount it once, in the shell. `{children}` is the one landmark every version of this
    # layout has, whatever else has been wrapped around it.
    if not APP_LAYOUT.exists():
        section.skip(f"missing {APP_LAYOUT}")
        return section
    layout = APP_LAYOUT.read_text()
    if "AppEditPortal" not in layout:
        hits = CHILDREN_RE.findall(layout)
        if len(hits) != 1:
            section.skip(
                f"expected exactly one `{{children}}` in {APP_LAYOUT}, found {len(hits)}",
                window(layout, "{children}"),
            )
            return section
        layout = CHILDREN_RE.sub(
            "{children}\n        <AppEditPortal />", layout, count=1
        )
        layout = add_import(layout, PORTAL_IMPORT)
        section.writes[APP_LAYOUT] = layout
        section.done.append("editor mounted once in the app shell")

    # And give the Apps Explorer a way to open it.
    if not EXPLORER.exists():
        section.skip(f"missing {EXPLORER}")
        return section
    explorer = EXPLORER.read_text()
    if "openAppEditor(" in explorer:
        return section
    hits = list(STORE_ICON_RE.finditer(explorer))
    if len(hits) != 1:
        section.skip(
            f"expected exactly one <StoreLinkIcon /> in the app cell, found {len(hits)}",
            window(explorer, "StoreLinkIcon"),
        )
        return section
    match = hits[0]
    explorer = explorer[: match.end()] + EDIT_BUTTON + explorer[match.end() :]
    explorer = add_import(explorer, EDITOR_IMPORT)
    section.writes[EXPLORER] = explorer
    section.done.append("Apps Explorer rows can open the editor in place")
    return section


# ─────────────────────────────────────────────────────────────────────────────
# D. Recon: the Spotlight board, so its Edit button is wired, not guessed
# ─────────────────────────────────────────────────────────────────────────────


def recon() -> None:
    print("\n" + "=" * 72)
    print("RECON (read-only) - the Spotlight board, in full")
    print("=" * 72)
    found = sorted(ROOT.glob("frontend/components/spotlight/*.tsx")) + sorted(
        ROOT.glob("frontend/app/(app)/spotlight/*.tsx")
    )
    if not found:
        print("  (no spotlight files)")
        return
    for path in found:
        lines = path.read_text().splitlines()
        print(f"\n--- {path}  ({len(lines)} lines)")
        for i, line in enumerate(lines, 1):
            print(f"  {i:>4}  {line}")


def main() -> int:
    if not (ROOT / "frontend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    for build in (section_glossary, section_sidebar_order, section_app_editor):
        build().commit()

    print(
        "\nPATCHED, NOT YET VERIFIED - the test run is the verification, not this script."
    )
    for note in notes:
        print(f"  - {note}")
    for entry in skipped:
        print()
        print(entry)

    recon()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
