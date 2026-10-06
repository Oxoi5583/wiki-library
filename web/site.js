/* No network requests: the scoped search index is embedded in each catalogue. */
(() => {
  "use strict";
  const themeButton = document.querySelector(".theme-toggle");
  const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
  const currentTheme = () =>
    document.documentElement.dataset.theme ||
    (systemTheme.matches ? "dark" : "light");
  const updateThemeLabel = () => {
    const dark = currentTheme() === "dark";
    themeButton?.setAttribute(
      "aria-label",
      dark ? "切換至淺色模式" : "切換至深色模式",
    );
    themeButton?.setAttribute(
      "title",
      dark ? "切換至淺色模式" : "切換至深色模式",
    );
  };
  themeButton?.addEventListener("click", () => {
    const theme = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("wiki-library-theme", theme);
    } catch (_) {
      /* Private mode is fine. */
    }
    updateThemeLabel();
  });
  systemTheme.addEventListener("change", updateThemeLabel);
  updateThemeLabel();

  const navigation = document.querySelector(".shelf-nav");
  const smallScreen = window.matchMedia("(max-width: 760px)");
  const sizeNavigation = () => {
    if (navigation) navigation.open = !smallScreen.matches;
  };
  smallScreen.addEventListener("change", sizeNavigation);
  sizeNavigation();

  const form = document.querySelector(".catalog-tools");
  const data = document.getElementById("catalog-data");
  if (!form || !data) return;
  const normalize = (value) =>
    String(value)
      .normalize("NFKC")
      .toLocaleLowerCase("zh-Hant")
      .replace(/\s+/g, " ")
      .trim();
  const entries = JSON.parse(data.textContent);
  entries.forEach((entry) => {
    entry.search = normalize(entry.search);
  });
  const list = document.querySelector(".catalogue .work-list");
  const rows = new Map(
    [...list.querySelectorAll(".work-row")].map((row) => [row.dataset.id, row]),
  );
  const count = document.getElementById("result-count");
  const empty = document.getElementById("empty-state");
  const fields = ["q", "media", "category", "series", "tag", "status", "sort"];
  const controls = Object.fromEntries(
    fields.map((name) => [name, form.elements.namedItem(name)]),
  );
  const defaults = {
    q: "",
    media: "",
    category: "",
    series: "",
    tag: "",
    status: "",
    sort: "added",
  };
  const collator = new Intl.Collator("zh-Hant", { numeric: true });
  const filters = ["media", "category", "series", "tag", "status"];
  const filterOptions = Object.fromEntries(
    filters.map((name) => [name, [...controls[name].options]]),
  );
  const valuesFor = (entry, name) => {
    if (name === "category") return entry.categories;
    if (name === "tag") return entry.tags;
    if (name === "series") return entry.series;
    return [entry[name]];
  };
  const matchesFilters = (entry, excluded = "") =>
    filters.every(
      (name) =>
        name === excluded ||
        !controls[name].value ||
        valuesFor(entry, name).includes(controls[name].value),
    );
  const availableValues = (items, name) =>
    new Set(
      items
        .filter((entry) => matchesFilters(entry, name))
        .flatMap((entry) => valuesFor(entry, name)),
    );
  const updateFilterOptions = (items) => {
    // Clear incompatible selections before rebuilding options. Removing a
    // constraint can only expand the available values for the other filters.
    const unavailable = filters.filter((name) => {
      const value = controls[name].value;
      return value && !availableValues(items, name).has(value);
    });
    unavailable.forEach((name) => {
      controls[name].value = "";
    });
    filters.forEach((name) => {
      const control = controls[name];
      const value = control.value;
      const available = availableValues(items, name);
      const options = filterOptions[name].filter(
        (option) => !option.value || available.has(option.value),
      );
      control.replaceChildren(...options);
      control.value = value;
    });
    return unavailable.length !== 0;
  };
  const readUrl = () => {
    // A previous render may have removed options needed by the restored URL.
    filters.forEach((name) => {
      controls[name].replaceChildren(...filterOptions[name]);
    });
    const params = new URLSearchParams(location.search);
    fields.forEach((name) => {
      const control = controls[name];
      const value = params.get(name) ?? defaults[name];
      control.value =
        control.tagName === "SELECT" &&
        ![...control.options].some((option) => option.value === value)
          ? defaults[name]
          : value;
    });
  };
  const writeUrl = () => {
    const url = new URL(location.href);
    fields.forEach((name) => {
      const value = controls[name].value;
      if (value && value !== defaults[name]) url.searchParams.set(name, value);
      else url.searchParams.delete(name);
    });
    try {
      history.replaceState(null, "", url);
    } catch (_) {
      /* Some file:// browsers disallow history changes. */
    }
  };
  const render = (save = true) => {
    const terms = normalize(controls.q.value).split(" ").filter(Boolean);
    const searched = entries.filter((entry) =>
      terms.every((term) => entry.search.includes(term)),
    );
    const filtersCleared = updateFilterOptions(searched);
    const visible = searched.filter((entry) => matchesFilters(entry));
    const order = controls.sort.value;
    visible.sort((a, b) => {
      if (order === "title") return collator.compare(a.title, b.title);
      if (order === "year")
        return (
          (Number(b.year) || 0) - (Number(a.year) || 0) ||
          collator.compare(a.title, b.title)
        );
      const dates = a.added.localeCompare(b.added);
      return (order === "oldest" ? dates : -dates) || a.id.localeCompare(b.id);
    });
    rows.forEach((row) => {
      row.hidden = true;
    });
    visible.forEach((entry) => {
      const row = rows.get(entry.id);
      row.hidden = false;
      list.appendChild(row);
    });
    count.textContent = visible.length;
    empty.hidden = visible.length !== 0;
    if (save || filtersCleared) writeUrl();
  };
  let timer;
  form.addEventListener("input", (event) => {
    if (event.target.name !== "q") return;
    clearTimeout(timer);
    timer = setTimeout(render, 100);
  });
  form.addEventListener("change", () => {
    clearTimeout(timer);
    render();
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    clearTimeout(timer);
    render();
  });
  form.addEventListener("reset", () => {
    clearTimeout(timer);
    setTimeout(() => {
      fields.forEach((name) => {
        controls[name].value = defaults[name];
      });
      render();
    }, 0);
  });
  window.addEventListener("popstate", () => {
    readUrl();
    render(false);
  });
  document.addEventListener("keydown", (event) => {
    if (
      event.key === "/" &&
      !event.ctrlKey &&
      !event.metaKey &&
      !event.altKey &&
      !event.target.matches('input, textarea, select, [contenteditable="true"]')
    ) {
      event.preventDefault();
      controls.q.focus();
    }
  });
  readUrl();
  render(false);
})();
