// ===== Mobile nav toggle =====
const navToggle = document.getElementById('navToggle');
const nav = document.getElementById('nav');
if (navToggle && nav) {
  navToggle.addEventListener('click', () => {
    const open = nav.classList.toggle('open');
    navToggle.setAttribute('aria-expanded', String(open));
  });
  nav.querySelectorAll('a').forEach((a) =>
    a.addEventListener('click', () => {
      nav.classList.remove('open');
      navToggle.setAttribute('aria-expanded', 'false');
    })
  );
}

// ===== Current year in footer =====
const yearEl = document.getElementById('year');
if (yearEl) yearEl.textContent = new Date().getFullYear();

// ===== Lead form handling =====
// NOTE: This is a front-end demo. To actually RECEIVE submissions, connect a
// backend or a form service (see README.md — Formspree, Netlify Forms, etc.).
document.querySelectorAll('.lead-form').forEach((form) => {
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const status = form.querySelector('.form-status');

    // Basic validation
    const name = form.querySelector('[name="name"]');
    const phone = form.querySelector('[name="phone"]');
    if (name && !name.value.trim()) {
      return setStatus(status, 'Please enter your name.', 'err');
    }
    if (phone && !phone.value.trim()) {
      return setStatus(status, 'Please enter a phone number.', 'err');
    }

    // Simulated success (replace with real submission — see README.md)
    setStatus(status, "Thanks! We received your info and will reach out shortly with your cash offer.", 'ok');
    form.reset();
  });
});

function setStatus(el, msg, type) {
  if (!el) return;
  el.textContent = msg;
  el.className = 'form-status ' + type;
}

// ===== Reveal-on-scroll animation =====
// Content is visible by default (in CSS/HTML). We only *animate* it in when
// JS + IntersectionObserver are available, and a safety timer guarantees
// everything becomes visible regardless — so a section never stays blank.
const revealEls = document.querySelectorAll('.card, .review, .step, .stat, .compare-col');
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function show(el) {
  el.style.opacity = '1';
  el.style.transform = 'none';
}

if ('IntersectionObserver' in window && !reduceMotion) {
  revealEls.forEach((el) => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(16px)';
    el.style.transition = 'opacity .5s ease, transform .5s ease';
  });
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          show(entry.target);
          io.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.12, rootMargin: '0px 0px -5% 0px' }
  );
  revealEls.forEach((el) => io.observe(el));

  // Safety net: never leave anything hidden (e.g. printing, full-page capture,
  // tabs that never fire the observer).
  window.addEventListener('load', () => setTimeout(() => revealEls.forEach(show), 1500));
  window.addEventListener('beforeprint', () => revealEls.forEach(show));
}
