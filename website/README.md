# A&B Rental Investments — "Sell Your House Fast For Cash" Website

A clean, modern, mobile-friendly **motivated-seller landing page** for
**A&B Rental Investments LLC** — built in the style of a "we buy houses for
cash" lead-capture site (like the readytosell.net reference). The whole point
of the page is to get a homeowner to submit their property for a cash offer.

It's plain static HTML/CSS/JS — no build step, no dependencies — so it's easy
to host anywhere and quick to customize.

## Files

| File | What it is |
|------|------------|
| `index.html` | All page content and structure |
| `styles.css` | All styling, colors, and responsive layout |
| `script.js` | Mobile menu, form handling, scroll animations |
| `assets/house.svg` | House/"SOLD" illustration (swap for a real photo) |

## Sections

Top call bar → hero with cash-offer form → trust stats → **How it works (3
steps)** → Why sell to us → **Cash offer vs. agent comparison** → situations we
help with (inherited, foreclosure, tired landlord, relocation, divorce,
repairs) → reviews → final cash-offer form → footer with disclaimer.

## View it locally

Open `index.html` in your browser, or run a tiny local server:

```bash
cd website
python3 -m http.server 8000
# then visit http://localhost:8000
```

## Customize it (the important part)

Everything you'll want to change is plain text in `index.html`. Search for these
placeholders and replace them:

- **`[Your Phone]`** — your phone number (appears in the top bar and contact
  section). Also update the `href="tel:+10000000000"` links with your real
  number, digits only, e.g. `tel:+15551234567`.
- **`[Your Email]`** — your email. Also update `href="mailto:info@abrentalinvestments.com"`.
- **`[Your City / Service Area]`** — the area you buy houses in. Mentioning your
  city throughout the page also helps local SEO (e.g. "We buy houses in
  Columbus, OH").
- **Trust stats** (7 Days, $0, etc.) — edit in the stats section.
- **Reviews** — replace the three sample quotes with real testimonials.
- **Situations** — edit the cards to match the sellers you work with.

### Add a real photo instead of the illustration

In `index.html`, replace:

```html
<img src="assets/house.svg" alt="Home bought by A&B Rental Investments" />
```

with a real image you add to `assets/`, e.g. `assets/house.jpg`.

### Change the colors

Open `styles.css` and edit the variables at the top (`:root`):

```css
--brand: #1f9d55;   /* primary green */
--accent: #f6b73c;  /* gold accent */
--navy: #12263a;    /* dark bar / footer */
```

## ⚠️ Make the forms actually reach you

Right now the cash-offer forms show a success message but **don't deliver
anywhere** (front-end demo). This is the most important step — without it you
won't receive leads. Easiest option, [Formspree](https://formspree.io):

1. Create a free Formspree account and get your form endpoint URL.
2. In `index.html`, change each `<form class="lead-form" ...>` to:
   ```html
   <form class="lead-form" action="https://formspree.io/f/yourID" method="POST">
   ```
3. In `script.js`, remove (or comment out) the `e.preventDefault()` line in the
   submit handler so the browser actually submits.

Other options: **Netlify Forms** (add `netlify` to the `<form>` tag if hosting
on Netlify), or your own backend. For faster response, also forward submissions
to your phone/email so you can call sellers back quickly — speed wins these deals.

## Publish it online (free options)

- **Netlify / Vercel / Cloudflare Pages** — drag-and-drop the `website` folder or
  connect this repo. Free custom-domain support.
- **GitHub Pages** — enable Pages in repo settings, point it at this folder.

## A note on the legal disclaimer

The footer includes a short disclaimer stating the site isn't a binding offer.
Keep (and have an attorney review) language like this, and make sure your
lead-capture practices comply with any applicable rules in your state.

---

Built as a strong starting point. Send me your real phone, email, service area,
and any real reviews and I'll drop them in — and I can tailor the copy (specific
city, specific situations you focus on) to match your market.
