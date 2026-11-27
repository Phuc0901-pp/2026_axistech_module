(function () {
  "use strict";

  document.addEventListener("contextmenu", function (e) {
    e.preventDefault();
  }, true);

  document.addEventListener("keydown", function (e) {
    var key = String(e.key || "").toUpperCase();
    var isDevTools =
      e.key === "F12" ||
      e.keyCode === 123 ||
      ((e.ctrlKey || e.metaKey) && e.shiftKey && (key === "I" || key === "J" || key === "C")) ||
      (e.metaKey && e.altKey && (key === "I" || key === "J" || key === "C" || key === "U")) ||
      (e.ctrlKey && !e.shiftKey && !e.altKey && key === "U");

    if (isDevTools) {
      e.preventDefault();
      e.stopPropagation();
    }
  }, true);
})();
