/** Single flag gating ALL demo (non-real) widgets. Off by default.
 *  See docs/DESIGN.md §3 for which widgets are demo and their would-be real source. */
export const SHOW_DEMO_WIDGETS =
  process.env.NEXT_PUBLIC_SHOW_DEMO_WIDGETS === "true";
