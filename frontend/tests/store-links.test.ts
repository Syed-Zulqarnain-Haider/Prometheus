import { describe, expect, it } from "vitest";

import { appStoreUrl, playStoreUrl, primaryStoreUrl } from "@/lib/store-links";

// These build URLs from app-master values that arrive from an upstream feed, so the
// encoding is a boundary, not a formality.
describe("store links", () => {
  it("builds a Play URL from a package name", () => {
    expect(playStoreUrl("com.terafort.game")).toBe(
      "https://play.google.com/store/apps/details?id=com.terafort.game",
    );
  });

  it("percent-encodes the package so it cannot escape the query parameter", () => {
    // An & in the id would otherwise start a second parameter, and a space would break
    // the URL outright - both are feed data, not something we control.
    expect(playStoreUrl("a&b c")).toBe(
      "https://play.google.com/store/apps/details?id=a%26b%20c",
    );
  });

  it("builds an App Store URL from a numeric or string id", () => {
    expect(appStoreUrl(1234567890)).toBe("https://apps.apple.com/app/id1234567890");
    expect(appStoreUrl("1234567890")).toBe("https://apps.apple.com/app/id1234567890");
  });

  it("returns null rather than a broken link when the id is missing", () => {
    expect(playStoreUrl(null)).toBeNull();
    expect(playStoreUrl("")).toBeNull();
    expect(appStoreUrl(undefined)).toBeNull();
    expect(appStoreUrl(0)).toBeNull();
    expect(primaryStoreUrl(null, null)).toBeNull();
  });

  it("prefers Play, and falls back to Apple when there is no package", () => {
    expect(primaryStoreUrl("com.x", 99)).toContain("play.google.com");
    expect(primaryStoreUrl(null, 99)).toBe("https://apps.apple.com/app/id99");
  });
});
