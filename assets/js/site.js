/* ==========================================================================
   Economic & Financial Intelligence Projects — shared site behaviour.

   Deliberately minimal. The portfolio is static: there is no form handling,
   no API call and no client-side data fetching. Everything here is a
   progressive enhancement over markup that already works without it:

     - keep the footer year from going stale;
     - mark the header once the page has scrolled;
     - drive the thin reading-progress rule under the header;
     - reveal sections as they enter the viewport (skipped under reduced
       motion, and never applied at all without JavaScript);
     - highlight the navigation link for the section in view;
     - wire the brief's Print / Save PDF control to window.print().
   ========================================================================== */
(function () {
  'use strict';

  var doc = document.documentElement;
  doc.classList.remove('no-js');
  doc.classList.add('js');

  var year = String(new Date().getFullYear());
  document.querySelectorAll('[data-current-year]').forEach(function (el) {
    el.textContent = year;
  });

  var reduceMotion = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var hasObserver = 'IntersectionObserver' in window;

  /* Header state and reading progress, batched into one frame per scroll. */
  var header = document.querySelector('.site-header');
  var progress = document.querySelector('.progress');
  var ticking = false;

  function onScroll() {
    var y = window.scrollY || window.pageYOffset;
    if (header) header.classList.toggle('is-scrolled', y > 8);
    if (progress) {
      var max = doc.scrollHeight - window.innerHeight;
      var ratio = max > 0 ? Math.min(1, Math.max(0, y / max)) : 0;
      progress.style.transform = 'scaleX(' + ratio.toFixed(4) + ')';
    }
    ticking = false;
  }
  window.addEventListener('scroll', function () {
    if (!ticking) { ticking = true; window.requestAnimationFrame(onScroll); }
  }, { passive: true });
  onScroll();

  /* Section reveal. Without an observer, or with reduced motion, content is
     simply shown: the CSS only hides [data-reveal] under html.js and
     prefers-reduced-motion: no-preference. */
  var revealTargets = document.querySelectorAll('[data-reveal]');
  if (!hasObserver || reduceMotion) {
    revealTargets.forEach(function (el) { el.classList.add('is-visible'); });
  } else {
    var revealer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          revealer.unobserve(entry.target);
        }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
    revealTargets.forEach(function (el) { revealer.observe(el); });
  }

  /* Print / Save PDF. The button ships hidden and is only revealed here, so a
     page without JavaScript never shows a control that cannot work. */
  document.querySelectorAll('[data-print]').forEach(function (btn) {
    btn.hidden = false;
    btn.addEventListener('click', function () { window.print(); });
  });

  /* Collapsed sections marked data-print-open are part of the document of
     record: open them for printing, then restore what the reader had. */
  var printOpened = [];
  window.addEventListener('beforeprint', function () {
    document.querySelectorAll('details[data-print-open]:not([open])').forEach(function (d) {
      d.open = true;
      printOpened.push(d);
    });
  });
  window.addEventListener('afterprint', function () {
    printOpened.forEach(function (d) { d.open = false; });
    printOpened = [];
  });

  /* Active navigation state: the link whose target section occupies the band
     just below the header. Applies to every nav that links to in-page ids,
     including the brief's table of contents. */
  var navLinks = Array.prototype.slice.call(
    document.querySelectorAll('.site-nav__link[href^="#"], .brief-toc a[href^="#"]')
  );
  if (hasObserver && navLinks.length) {
    var byId = {};
    navLinks.forEach(function (link) {
      var id = decodeURIComponent(link.getAttribute('href').slice(1));
      if (!id) return;
      (byId[id] = byId[id] || []).push(link);
    });

    var sections = Object.keys(byId)
      .map(function (id) { return document.getElementById(id); })
      .filter(Boolean);

    var setActive = function (id) {
      navLinks.forEach(function (link) {
        var on = link.getAttribute('href') === '#' + id;
        link.classList.toggle('is-active', on);
        if (on) link.setAttribute('aria-current', 'location');
        else link.removeAttribute('aria-current');
      });
    };

    var spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) setActive(entry.target.id);
      });
    }, { rootMargin: '-30% 0px -60% 0px', threshold: 0 });
    sections.forEach(function (s) { spy.observe(s); });
  }
})();
