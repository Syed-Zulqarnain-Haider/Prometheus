/* ============================================================================
   ROUTER — client-side nav between dashboard pages.
   ----------------------------------------------------------------------------
   Overview is static markup (#page-overview). Every other nav item maps to a
   builder in window.PAGES and renders into #page-dynamic. The shared topbar
   title/subtitle update per page. Current page persists in the URL hash +
   localStorage so a refresh keeps you where you were.
   ============================================================================ */
(function () {
  const titleEl = document.querySelector(".topbar__title");
  const subEl = document.querySelector(".topbar__subtitle");
  const overview = document.getElementById("page-overview");
  const dynamic = document.getElementById("page-dynamic");
  const OVERVIEW = { title: "CEO COMMAND CENTER", subtitle: "Real-time overview of Terafort performance" };

  function setActive(key) {
    document.querySelectorAll(".nav__item:not(.is-header)").forEach((n) =>
      n.classList.toggle("is-active", n.getAttribute("data-page-key") === key));
  }

  function go(key, fromUser) {
    const builder = window.PAGES && window.PAGES[key];
    if (key === "overview" || !builder) {
      key = "overview";
      dynamic.hidden = true;
      dynamic.innerHTML = "";
      overview.hidden = false;
      titleEl.textContent = OVERVIEW.title;
      subEl.textContent = OVERVIEW.subtitle;
    } else {
      let page;
      try { page = builder(); }
      catch (e) { console.error("Page build failed:", key, e); return; }
      dynamic.innerHTML = "";
      dynamic.appendChild(page.node);
      page.node.classList.add("page-enter");
      overview.hidden = true;
      dynamic.hidden = false;
      titleEl.textContent = page.title;
      subEl.textContent = page.subtitle;
    }
    setActive(key);
    localStorage.setItem("tf-page", key);
    if (location.hash.slice(1) !== key) {
      history.replaceState(null, "", "#" + key);
    }
    if (fromUser) window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // wire nav clicks (all items, including the CEO Dashboard header)
  document.querySelectorAll(".nav__item[data-page-key]").forEach((item) => {
    item.addEventListener("click", () => go(item.getAttribute("data-page-key"), true));
  });

  // restore from hash or storage
  const initial = (location.hash.slice(1)) || localStorage.getItem("tf-page") || "overview";
  go(initial, false);

  window.addEventListener("hashchange", () => {
    const k = location.hash.slice(1) || "overview";
    if (k !== (localStorage.getItem("tf-page") || "overview")) go(k, false);
  });

  window.__goPage = go; // exposed for debugging / deep-linking
})();
