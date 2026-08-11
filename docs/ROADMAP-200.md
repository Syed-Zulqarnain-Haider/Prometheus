# Prometheus - Top 200 additions (owner-approved backlog)

Requested 2026-08-11: a full-platform review plus the 200 things worth adding, listed
before anything is built. Priorities: **P1** = build now, **P2** = next wave, **P3** =
later/needs a decision. Items marked `[srv]` need deployed-only files and get built via
anchored patch scripts; items marked `[dec]` need one owner decision before they can ship.

## A. Executive overview & analytics depth (1-24)

1. **P1** Revenue drill-down: click Revenue → AdMob vs AppLovin split (already requested) `[srv]`
2. **P1** UA spend drill-down by network; installs drill-down paid vs organic vs store `[srv]`
3. **P1** Per-app platform split: iOS vs Android side by side on App Detail
4. **P2** Week-over-week / month-over-month auto-commentary ("Revenue up 12%, driven by X")
5. **P2** Cohort view: revenue by install-week cohort from existing daily data
6. **P2** Rolling averages toggle (7d/28d) on every timeseries to smooth weekday cycles
7. **P2** Weekday/weekend seasonality panel (avg by day-of-week)
8. **P1** "Top movers" card: apps with the largest Δ vs previous period, up and down
9. **P2** Contribution waterfall: which apps added/lost the most revenue this period
10. **P2** Pareto chart: cumulative % of revenue by app rank (the 80/20 view)
11. **P3** Simple forecast band on revenue trend (linear + seasonal, clearly labeled estimate)
12. **P2** Target vs actual pacing on Overview: month-to-date against the monthly target
13. **P2** Break-even day marker: first day of month cumulative profit turned positive
14. **P3** Per-HOU scorecards page (one row per head-of-unit, their KPIs)
15. **P2** Publisher league table with period deltas
16. **P3** Custom KPI builder: pick any registry column pair as a ratio card `[dec]`
17. **P2** ARPDAU-style normalization: revenue per install where installs exist
18. **P2** "Data through" per-metric footnote (Apple lag vs Adjust lag differ)
19. **P3** Annotations: pin a note to a date ("UA push started"), shown on all charts
20. **P2** Anomaly badges on charts: dot where a value is >3σ from trailing mean
21. **P3** Goal lines on any chart from the targets table
22. **P2** Period presets "This month / Last month / QTD / YTD" added to the date picker
23. **P2** Fiscal-week numbering option in date grouping `[dec]`
24. **P3** Executive email digest v2: top movers + pacing + anomalies (extends digest) `[srv]`

## B. Drill-downs & exploration (25-38)

25. **P1** Every KPI card clickable → opens the matching page pre-filtered
26. **P1** Breakdown table rows clickable → drill into that dimension value
27. **P2** Explore: second dimension (group by pod THEN platform)
28. **P2** Explore: save an exploration as a Saved View directly
29. **P2** Cross-highlight: hover a legend entry dims other series across the page
30. **P3** Right-click/long-press context menu on chart points: "filter to this", "exclude"
31. **P2** Time drill: click a month bucket → re-bucket that range by day
32. **P2** App Detail: mini-breakdown tabs (revenue sources, installs sources, costs)
33. **P3** Path-style flow: installs → paying users → revenue funnel per app `[dec]` (needs event data)
34. **P2** "Compare these" checkbox on Apps Explorer rows → sends selection to Compare
35. **P2** Compare: per-app A-vs-B (pick one app, compare its two periods)
36. **P2** Compare: dimension compare mode (iOS vs Android same period) `[req]`
37. **P3** Global search (Cmd+K): apps, pages, saved views, admin users
38. **P2** Recently viewed apps list on Apps Explorer

## C. Charts & visualization (39-52)

39. **P1** Number formatting consistency pass: same compact/full rules everywhere
40. **P2** Export any chart as PNG (ECharts built-in, one button)
41. **P2** Copy chart data to clipboard as TSV
42. **P2** Fullscreen mode per chart
43. **P2** Brush-to-zoom on timeseries with reset
44. **P3** Small-multiples view: one mini-chart per app for a chosen metric
45. **P2** Consistent empty/error/loading states via one shared ChartState component
46. **P2** Show data table under any chart (accessibility + verification)
47. **P3** Calendar heatmap of daily revenue (GitHub-style)
48. **P2** Dual-axis guardrail: only allow when units differ, label both axes
49. **P2** Legend overflow: collapse >8 series into "top 7 + Other"
50. **P3** Per-chart color-by-dimension option (color by platform vs by app)
51. **P2** Print stylesheet for report pages
52. **P3** Motion-reduced mode respecting prefers-reduced-motion

## D. Filters & navigation UX (53-64)

53. **P1** Filter chips row: active filters as removable chips under the bar
54. **P2** Filter presets: save/recall named filter sets per user
55. **P2** "Only my scope" quick toggle for pod owners
56. **P2** Dropdown counts: show how many rows each option would keep (faceted counts)
57. **P2** Multi-select keyboard support: type-ahead + space to toggle
58. **P3** URL shortener for shared filter states (long URLs today)
59. **P2** Sticky filter bar on scroll with condensed height
60. **P1** Mobile filter drawer polish: full-height sheet, apply/clear footer
61. **P2** Per-page default date ranges (Store wants 7d, Revenue 30d) `[dec]`
62. **P2** Breadcrumbs on App Detail / drill-down pages
63. **P2** Keyboard shortcuts: g+o Overview, g+r Revenue, ? for help sheet
64. **P3** Onboarding tour v2 covering chat, compare, profile

## E. Compare (65-70)

65. **P2** Three-period compare (A/B/C) for launch analysis `[dec]`
66. **P1** Compare: normalized mode (per-day averages when periods differ in length)
67. **P2** Compare: highlight rows with |Δ| above a threshold
68. **P2** Compare: export the A-vs-B table
69. **P2** Top-apps widget: "show as table only" toggle for >5 apps
70. **P2** Compare deep-link presets: "vs last month" URL preset

## F. Apps Explorer & App Master (71-85)

71. **P1** App Master: newly-synced apps pinned to top (already requested) `[srv]`
72. **P1** App Master: "needs review" filter surfaced as a default tab `[srv]`
73. **P2** App Master: bulk edit (set pod owner on N selected rows)
74. **P2** App Master: edit history per row (who changed what, when)
75. **P2** Apps Explorer: column presets (Finance view, UA view, Store view)
76. **P2** Apps Explorer: pin favorite apps to top per user
77. **P2** Apps Explorer: conditional formatting (red profit, green ROAS) with thresholds
78. **P2** Apps Explorer: totals row that respects current filters
79. **P3** App archival: hide dead apps from pickers, keep history `[dec]`
80. **P2** App icons in every app list (icon service exists for iOS; add Play) `[srv]`
81. **P2** App Detail: store listing links + package copy button
82. **P3** App notes: freeform notes per app, visible on App Detail
83. **P2** is_mapped=false apps: banner count on Apps Explorer linking to Data Health
84. **P3** New-app checklist workflow (map, assign pod, set target) `[dec]`
85. **P2** App Master: CSV import for bulk metadata `[dec]`

## G. Revenue / UA / Store pages (86-97)

86. **P1** Revenue: AdMob vs AppLovin stacked area + share-of-revenue % (needs #1 columns)
87. **P2** Revenue: IAP vs Ads mix trend
88. **P2** Revenue: refund/chargeback visibility if columns exist `[srv]`
89. **P2** UA: spend vs paid installs dual chart with CPI overlay
90. **P2** UA: ROAS by spend-band scatter (which spend levels pay back)
91. **P2** UA: network share table (needs #2 columns)
92. **P2** Store: impressions → page views → installs conversion funnel where columns exist
93. **P2** Store: organic share trend with paid overlay
94. **P2** Store: uninstall trend chart (raw counts, owner rule: no rate)
95. **P3** Store: ratings trend if the sync carries ratings columns `[srv]`
96. **P2** Per-page "About this data" popover: definitions from the glossary inline
97. **P2** Country/geo breakdown IF the view carries geo columns, else document absence `[srv]`

## H. Reports & exports (98-109)

98. **P2** Scheduled report health panel: last run, next run, failures `[srv]`
99. **P2** Report builder: chart blocks, not just tables `[dec]`
100. **P2** Export: XLSX with a metadata sheet (filters used, generated-by, RBAC role)
101. **P2** Export progress toast with cancel for big exports
102. **P3** Report templates: quarterly review, UA weekly, store health
103. **P2** Share links that pin the data date so recipients see identical numbers
104. **P3** Public read-only report snapshot pages with expiry `[dec]` (security review first)
105. **P2** Export audit view for admins: who exported what, when
106. **P2** Saved views: folders/tags once count grows
107. **P3** Report comments: discuss a report inline (reuses chat infra)
108. **P2** "Email me this view weekly" one-click from any page `[srv]`
109. **P3** Slack/webhook delivery for scheduled reports `[dec]`

## I. Alerts & notifications (110-121)

110. **P1** Clickable notifications everywhere: every type carries a deep link (requested) `[srv]`
111. **P2** Per-user alert thresholds (my apps only, my ROAS floor)
112. **P2** Alert mute/snooze per rule
113. **P2** Notification preferences page: in-app / email per category
114. **P2** Digest of unread notifications if away >24h `[srv]`
115. **P2** Alert on sync failure visible to admins as banner, not just notification
116. **P2** Alert history page with resolution state
117. **P3** Composite alerts (revenue down AND spend up)
118. **P2** New-app-synced notification to admins (pairs with #71)
119. **P3** Threshold suggestions from history (auto-suggest 3σ)
120. **P2** Browser tab title unread count "(3) Prometheus"
121. **P3** Web push notifications `[dec]` (needs service worker + user consent)

## J. Chat & collaboration (122-135)

122. **P1** Unread chat badge on the sidebar Chat entry (uses existing unread_total)
123. **P2** Group conversations UI (backend already models kind=group)
124. **P2** Share a chart/view into chat as a rich link card
125. **P2** Message search within a conversation
126. **P2** Emoji reactions (one table, additive migration)
127. **P3** File/image attachments `[dec]` (size/storage policy first)
128. **P2** Typing indicator via presence-style Redis key
129. **P2** Edit own message within 15 minutes (edited_at column already exists)
130. **P2** Desktop notification on new message when tab unfocused (in-app permission)
131. **P3** Message pinning per conversation
132. **P2** "Message" button on people directory and profile pages
133. **P2** Chat widget: floating launcher on all pages (Attmosfire style) with unread dot
134. **P3** Broadcast announcements: admin → everyone, read receipts
135. **P3** Retention policy for messages `[dec]` (compliance decision)

## K. Profile, presence & people (136-142)

136. **P2** People directory page: full-page version of the presence menu with search
137. **P2** Working-hours display from profile timezone ("3:40 AM for them")
138. **P2** Status message ("On leave till Monday") shown in chat + directory
139. **P3** Out-of-office auto-flag from status
140. **P2** Avatar crop/resize client-side before upload (canvas, no new deps)
141. **P2** Profile completeness nudge (no name set → banner once)
142. **P3** Org chart view from pod ownership data `[dec]`

## L. Admin & RBAC (143-156)

143. **P1** Admin: user detail drawer consolidating roles, scopes, activity, sessions
144. **P2** Role permission matrix editor UI (view exists server-side) `[srv]`
145. **P2** Scope simulator: "view as role X" preview for admins (read-only)
146. **P2** Bulk user import via CSV `[dec]`
147. **P2** Access request flow v2: requester sees status, admin sees queue count badge
148. **P2** Admin action confirmations with typed confirmation for destructive ops
149. **P1** Step-up re-auth: 15-min freshness for critical admin actions (requested)
150. **P2** Session list per user with device/IP, admin-revocable individually `[srv]`
151. **P2** Audit log: saved filters + CSV export + retention display
152. **P3** Audit anomaly view: unusual export volume or off-hours admin activity
153. **P2** Admin dashboard: platform stats (DAU of the dashboard itself, top pages)
154. **P3** Feature flags table for gradual rollouts `[dec]`
155. **P2** Maintenance banner: admin-set message shown to everyone
156. **P3** Config change log: settings edits shown as timeline (audit exists; surface it)

## M. Security hardening (157-168)

157. **P1** Re-auth freshness check dependency (auth_time ≤ 15 min) for marked routes
158. **P2** CSP with nonces for scripts (currently only frame-ancestors) `[dec]` (breakage risk)
159. **P2** Subresource integrity / self-host the Google Fonts css (external fetch today)
160. **P2** Login anomaly notice: "new device signed in" notification `[srv]`
161. **P2** Rate-limit headers exposed (X-RateLimit-Remaining) so the UI can back off
162. **P2** Failed-login lockout surfacing in admin (Firebase handles auth; surface events)
163. **P2** Avatar upload: strip EXIF metadata server-side (Pillow, already feasible)
164. **P2** Chat abuse guard: max messages/minute per user (Redis, mirrors rate limiter)
165. **P3** IP allowlist option for admin panel routes `[dec]`
166. **P2** Dependency audit in CI: pip-audit + npm audit as non-blocking report
167. **P2** Secrets scan pre-commit hook shipped in repo (mirrors setup-branches guard)
168. **P3** Security.txt + internal security contact page

## N. Performance & caching (169-178)

169. **P1** Batch unread counts in messaging list (kill the N+1 - audit confirmed)
170. **P2** HTTP cache headers on /apps and /meta endpoints (they change daily)
171. **P2** Frontend bundle: lazy-load chat page code (only loads when visited)
172. **P2** Virtualize the App Master table (TanStack Virtual is already a dependency)
173. **P2** Debounce people-search and app-search inputs (300ms)
174. **P2** Avatar object-URL revocation on unmount (leak found in audit)
175. **P2** Conversation list: skip presence lookups when the tab is hidden
176. **P3** Switch chat polling to SSE once nginx passes upgrade headers `[dec]`
177. **P2** DB: composite index audit for new tables after a month of real usage
178. **P3** Read replica story if user count grows past ~200 `[dec]`

## O. Data quality & sync ops (179-188)

179. **P2** Sync run diff summary: rows added/updated per run, visible in Data Health
180. **P2** Column drift alarm: view columns vs registry mismatch banner for admins
181. **P2** Freshness SLO tracking: % of days data arrived by 07:00 UTC
182. **P2** Backfill runner UI with progress + audit (range mode exists) `[srv]`
183. **P2** Data dictionary page generated from the metric registry (source of truth)
184. **P3** Dry-run sync mode showing would-be changes
185. **P2** Zero-day detector: flag a source reporting exactly 0 after 30d of nonzero
186. **P3** Reconciliation report: BQ totals vs Postgres totals daily checksum
187. **P2** Late-arriving data marker on charts (Apple 2-3 day lag shading)
188. **P3** Manual correction workflow with audit trail `[dec]` (contradicts UPSERT purity)

## P. Observability & reliability (189-194)

189. **P2** /metrics endpoint (Prometheus-the-tool format) for the dashboard itself `[srv]`
190. **P2** Frontend error boundary + client error reporting to backend log
191. **P2** Slow-query log surfacing in admin System tab
192. **P2** Uptime/health history page (ping table already exists via health checks)
193. **P3** Synthetic check: cron hits /health + one authed metric endpoint, alerts on fail
194. **P3** Backup verification: weekly restore-test job with report `[dec]`

## Q. Mobile & accessibility (195-200)

195. **P1** Chat page responsive: list/thread stacked navigation below md (panes today)
196. **P2** Touch targets ≥44px audit pass on filter bar and tables
197. **P2** Focus-visible rings consistent with the new theme
198. **P2** Screen-reader labels for presence dots ("Ayesha, online")
199. **P2** aria-live region for new chat messages
200. **P3** PWA manifest + icon so the dashboard installs on phones `[dec]`

---

## Implementation order (starting immediately, no further sign-off)

1. **Audit fixes** from the two review passes (bugs come before features).
2. **P1 items**: 1, 2, 3, 8, 25, 26, 39, 53, 60, 66, 71, 72, 86, 110, 122, 143, 149, 157,
   169, 174, 195 - the requested drill-downs, App Master ordering, step-up re-auth, chat
   badge/responsiveness, and the N+1/leak fixes.
3. **P2 waves** grouped by page so each deploy is testable in one place.
4. **P3/[dec] items** get built once their one-line decision is answered; each is listed
   with what's needed.

Blocked inputs, still open: the metric-registry column listing (unblocks 1, 2, 86, 91),
GitLab availability (promotion bookkeeping), SMTP details (email activation, 108, 114).
