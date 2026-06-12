/** Public app-store URLs, built only when the respective store ID exists. */

export function playStoreUrl(androidPackage: string | null | undefined): string | null {
  return androidPackage
    ? `https://play.google.com/store/apps/details?id=${encodeURIComponent(androidPackage)}`
    : null;
}

export function appStoreUrl(appleId: number | string | null | undefined): string | null {
  return appleId ? `https://apps.apple.com/app/id${appleId}` : null;
}

/** A single best store URL (prefers Google Play), for the inline table icon. */
export function primaryStoreUrl(
  androidPackage: string | null | undefined,
  appleId: number | string | null | undefined,
): string | null {
  return playStoreUrl(androidPackage) ?? appStoreUrl(appleId);
}
