/* ==========================================================================
   Economic & Financial Intelligence Projects — shared site behaviour.

   Deliberately minimal. The portfolio is static: there is no form handling,
   no API call and no client-side data fetching in this phase. The only job
   here is to keep the footer year from going stale, applied as a
   progressive enhancement over the year already present in the markup.
   ========================================================================== */
(function () {
  'use strict';

  var year = String(new Date().getFullYear());

  document.querySelectorAll('[data-current-year]').forEach(function (el) {
    el.textContent = year;
  });
})();
