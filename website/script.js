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
    setStatus(status, 'Thanks! We received your request and will be in touch soon.', 'ok');
    form.reset();
  });
});

function setStatus(el, msg, type) {
  if (!el) return;
  el.textContent = msg;
  el.className = 'form-status ' + type;
}

// ===== Reveal-on-scroll animation =====
const revealEls = document.querySelectorAll('.card, .review, .gallery-item, .stat');
if ('IntersectionObserver' in window) {
  revealEls.forEach((el) => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(16px)';
    el.style.transition = 'opacity .5s ease, transform .5s ease';
  });
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.style.opacity = '1';
          entry.target.style.transform = 'none';
          io.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15 }
  );
  revealEls.forEach((el) => io.observe(el));
}
