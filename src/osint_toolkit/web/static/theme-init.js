/* Anti-flash theme bootstrap — must run before CSS paint */
(function () {
  var KEY = "osint-theme";
  var pref = "system";
  try {
    pref = localStorage.getItem(KEY) || "system";
  } catch (_) {}
  var dark =
    pref === "dark" ||
    (pref === "system" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.documentElement.dataset.themePref = pref;
})();
