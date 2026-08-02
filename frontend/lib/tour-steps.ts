/** Steps for the in-app product tour. Each step optionally targets an element by a CSS
 * selector (a `data-tour="…"` attribute); a step with no selector is shown centered (the
 * welcome/finish cards). Steps whose target isn't on the current page are skipped, so the
 * same tour works from any page. */
export interface TourStep {
  selector?: string;
  title: string;
  body: string;
  placement?: "top" | "bottom" | "left" | "right";
}

export const TOUR_STEPS: TourStep[] = [
  {
    title: "Welcome to Prometheus 👋",
    body: "A 60-second tour of the dashboard. You can replay it anytime from the ? button in the top bar.",
  },
  {
    selector: "[data-tour='nav']",
    title: "Navigate the workspace",
    body: "Jump between Overview, Revenue, UA, Store, Apps and Admin. Hit the grip to drag pages into the order you like — it's saved for you.",
    placement: "right",
  },
  {
    selector: "[data-tour='filters']",
    title: "Global filters",
    body: "Filter the ENTIRE dashboard by date, platform, pod, publisher and more. Filters sync to the URL, so you can copy the link to share the exact view.",
    placement: "bottom",
  },
  {
    selector: "[data-tour='kpis']",
    title: "Reported KPIs",
    body: "Your finance-authoritative headline numbers — revenue, spend, profit and the reported P&L ladder — for the selected period, with period-over-period deltas.",
    placement: "bottom",
  },
  {
    selector: "[data-tour='notifications']",
    title: "Notifications",
    body: "Share approvals, access requests and newly-discovered apps land here. Click a notification to jump straight to where it happened.",
    placement: "bottom",
  },
  {
    selector: "[data-tour='help']",
    title: "Replay this tour anytime",
    body: "Click the ? button whenever you want to see this walkthrough again. That's it — enjoy exploring!",
    placement: "bottom",
  },
];
