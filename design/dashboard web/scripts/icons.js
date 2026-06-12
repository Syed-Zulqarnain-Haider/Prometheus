/* ============================================================================
   ICONS — minimal stroke icon set (24×24 viewBox, currentColor).
   Each entry is the INNER markup of an <svg>. Helper icon(name, size).
   ============================================================================ */
window.ICONS = {
  // brand
  bolt:   '<path d="M13 2 4 14h7l-1 8 9-12h-7z" fill="currentColor" stroke="none"/>',
  // nav
  grid:   '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  home:   '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/>',
  bank:   '<path d="M3 9 12 4l9 5"/><path d="M5 9v9M9 9v9M15 9v9M19 9v9"/><path d="M3 21h18"/>',
  target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1" fill="currentColor"/>',
  stack:  '<rect x="4" y="4" width="16" height="6" rx="1.5"/><rect x="4" y="14" width="16" height="6" rx="1.5"/>',
  factory:'<path d="M3 21V10l6 4V10l6 4V6l6 3v12z"/><path d="M3 21h18"/>',
  users:  '<circle cx="9" cy="8" r="3.2"/><path d="M3.5 20a5.5 5.5 0 0 1 11 0"/><path d="M16 5.5a3 3 0 0 1 0 5.6"/><path d="M17 14.5a5.2 5.2 0 0 1 3.5 5"/>',
  spark:  '<path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><path d="M6.3 6.3l2.6 2.6M15.1 15.1l2.6 2.6M6.3 17.7l2.6-2.6M15.1 8.9l2.6-2.6"/>',
  person: '<circle cx="12" cy="8" r="3.5"/><path d="M5 20a7 7 0 0 1 14 0"/>',
  doc:    '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M9 12h6M9 16h6"/>',
  bell:   '<path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  // controls
  calendar:'<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 9h17M8 3v4M16 3v4"/>',
  chevron: '<path d="M6 9l6 6 6-6"/>',
  arrowR:  '<path d="M5 12h14M13 6l6 6-6 6"/>',
  arrowUp: '<path d="M7 14l5-5 5 5" stroke-width="2.4"/>',
  arrowDn: '<path d="M7 10l5 5 5-5" stroke-width="2.4"/>',
  sun:     '<circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.4M12 19.1v2.4M21.5 12h-2.4M4.9 12H2.5M18.7 5.3l-1.7 1.7M7 17l-1.7 1.7M18.7 18.7 17 17M7 7 5.3 5.3"/>',
  moon:    '<path d="M20 14.5A8 8 0 0 1 9.5 4a7 7 0 1 0 10.5 10.5z"/>',
  // factory pipeline
  bulb:   '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 1 4 10.5c-.7.6-1 1.3-1 2.5H9c0-1.2-.3-1.9-1-2.5A6 6 0 0 1 12 3z"/>',
  box:    '<path d="M12 3 4 7v10l8 4 8-4V7z"/><path d="M4 7l8 4 8-4M12 11v10"/>',
  flask:  '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4A2 2 0 0 0 19 18l-5-9V3"/><path d="M7.5 15h9"/>',
  ship:   '<path d="M5 8h14l-1.5 5H6.5z"/><path d="M12 3v5M8 21h8M12 13v8"/>',
  kill:   '<circle cx="12" cy="12" r="8.5"/><path d="M8.5 8.5l7 7M15.5 8.5l-7 7"/>',
};

window.icon = function (name, size) {
  size = size || 18;
  const inner = window.ICONS[name] || "";
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`;
};
