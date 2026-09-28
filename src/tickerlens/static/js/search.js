/* Search combobox for Tickerlens (PRD §4.10).
 *
 * Attach with: <input data-search-combobox ...>
 * The script wraps each such input in a relative container, fetches ranked
 * suggestions from /api/search as the user types (150 ms debounce), and
 * provides full keyboard support: ArrowUp/ArrowDown to move, Enter to open,
 * Escape to dismiss. Selecting a row navigates to /company/{ticker}.
 */
(function () {
  "use strict";

  var DEBOUNCE_MS = 150;

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[c];
    });
  }

  function highlight(text, query) {
    var idx = text.toLowerCase().indexOf(query.toLowerCase());
    if (idx < 0 || !query) return escapeHtml(text);
    var before = escapeHtml(text.slice(0, idx));
    var match = escapeHtml(text.slice(idx, idx + query.length));
    var after = escapeHtml(text.slice(idx + query.length));
    return before + "<mark>" + match + "</mark>" + after;
  }

  function initSearchCombobox(input) {
    if (input.dataset.comboboxInit) return;
    input.dataset.comboboxInit = "1";
    input.setAttribute("autocomplete", "off");
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-autocomplete", "list");

    var wrap = document.createElement("div");
    wrap.className = "relative";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    var dropdown = document.createElement("div");
    dropdown.className =
      "absolute z-50 mt-1 w-full max-h-72 overflow-auto rounded-lg " +
      "bg-gray-900 border border-gray-700 shadow-xl";
    dropdown.setAttribute("role", "listbox");
    dropdown.hidden = true;
    wrap.appendChild(dropdown);

    var results = [];
    var activeIndex = -1;
    var debounceTimer = null;
    var lastQuery = null;

    function close() {
      dropdown.hidden = true;
      input.setAttribute("aria-expanded", "false");
      activeIndex = -1;
    }

    function openTo(ticker) {
      window.location = "/company/" + encodeURIComponent(ticker);
    }

    function setActive(i) {
      activeIndex = i;
      var rows = dropdown.querySelectorAll("[role=option]");
      rows.forEach(function (row, j) {
        if (j === i) {
          row.classList.add("bg-indigo-600/40");
          row.setAttribute("aria-selected", "true");
          row.scrollIntoView({ block: "nearest" });
        } else {
          row.classList.remove("bg-indigo-600/40");
          row.setAttribute("aria-selected", "false");
        }
      });
    }

    function render(query) {
      dropdown.innerHTML = "";
      if (!results.length) {
        var empty = document.createElement("div");
        empty.className = "px-4 py-3 text-sm text-gray-500";
        empty.textContent = "No companies found for '" + query + "'";
        dropdown.appendChild(empty);
      } else {
        results.forEach(function (r, i) {
          var row = document.createElement("div");
          row.setAttribute("role", "option");
          row.setAttribute("aria-selected", "false");
          row.className =
            "px-4 py-2.5 cursor-pointer text-sm flex items-baseline gap-2 " +
            "hover:bg-gray-800 border-b border-gray-800/50 last:border-0";
          var tickerEl = highlight(r.ticker, query);
          var nameEl = highlight(r.name, query);
          row.innerHTML =
            '<span class="font-bold text-white shrink-0">' +
            tickerEl +
            '</span><span class="text-gray-400 truncate">' +
            nameEl +
            "</span>";
          // mousedown fires before input blur, so selection wins over dismiss
          row.addEventListener("mousedown", function (e) {
            e.preventDefault();
            openTo(r.ticker);
          });
          row.addEventListener("mousemove", function () {
            setActive(i);
          });
          dropdown.appendChild(row);
        });
      }
      dropdown.hidden = false;
      input.setAttribute("aria-expanded", "true");
      setActive(results.length ? 0 : -1);
    }

    function search(query) {
      if (query === lastQuery) return;
      lastQuery = query;
      if (!query) {
        close();
        return;
      }
      fetch("/api/search?q=" + encodeURIComponent(query))
        .then(function (resp) {
          return resp.json();
        })
        .then(function (data) {
          if (input.value.trim() !== query) return; // stale response
          results = data.results || [];
          render(query);
        })
        .catch(function () {
          close();
        });
    }

    input.addEventListener("input", function () {
      clearTimeout(debounceTimer);
      var query = input.value.trim();
      debounceTimer = setTimeout(function () {
        search(query);
      }, DEBOUNCE_MS);
    });

    input.addEventListener("focus", function () {
      var query = input.value.trim();
      if (query) search(query);
    });

    input.addEventListener("keydown", function (e) {
      if (dropdown.hidden) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive(results.length ? (activeIndex + 1) % results.length : -1);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive(
          results.length
            ? (activeIndex - 1 + results.length) % results.length
            : -1
        );
      } else if (e.key === "Enter") {
        e.preventDefault();
        var pick =
          results[activeIndex] || results[0] || null;
        if (pick) {
          openTo(pick.ticker);
        } else {
          // No suggestions: fall back to the raw text (friendly 404 if unknown).
          var raw = input.value.trim();
          if (raw) openTo(raw.toUpperCase());
        }
      } else if (e.key === "Escape") {
        e.preventDefault();
        close();
      }
    });

    input.addEventListener("blur", function () {
      // Delay so a mousedown on a row still registers first.
      setTimeout(close, 120);
    });

    document.addEventListener("click", function (e) {
      if (!wrap.contains(e.target)) close();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document
      .querySelectorAll("input[data-search-combobox]")
      .forEach(initSearchCombobox);
  });
})();
