# AB Rentals — Website

A clean, modern, mobile-friendly landing page for **AB Rentals**, built as a
lead-capture site (similar in style to readytosell.net landing pages). It's a
single static page — no build step, no dependencies — so it's easy to host
anywhere and quick to customize.

## Files

| File | What it is |
|------|------------|
| `index.html` | All page content and structure |
| `styles.css` | All styling, colors, and responsive layout |
| `script.js` | Mobile menu, form handling, scroll animations |
| `assets/about.svg` | Placeholder illustration (swap for a real photo) |

## View it locally

Just open `index.html` in your browser. Or run a tiny local server:

```bash
cd website
python3 -m http.server 8000
# then visit http://localhost:8000
```

## Customize it (the important part)

Everything you'll want to change is plain text in `index.html`. Search for these
placeholders and replace them:

- **`[Your Phone]`** — your phone number. Also update the `href="tel:+10000000000"`
  links (use your real number, digits only, e.g. `tel:+15551234567`).
- **`[Your Email]`** — your email. Also update `href="mailto:hello@abrentals.com"`.
- **`[Your Address / Service Area]`** — where you operate.
- **Stats** (Years, Customers, etc.) — edit the numbers in the "stats" section.
- **Services** — edit the six cards under "What We Offer" to match what you rent.
- **Reviews** — replace the sample quotes and names with real testimonials.
- **Gallery** — replace the colored "Photo 1–6" boxes with real images
  (see below).

### Add real photos to the gallery

In `index.html`, replace a gallery box like:

```html
<div class="gallery-item" style="--i:1">Photo 1</div>
```

with an image:

```html
<div class="gallery-item"><img src="assets/photo1.jpg" alt="Description" /></div>
```

Put your image files in the `assets/` folder.

### Change the colors

Open `styles.css` and edit the variables at the top (`:root`). The main ones:

```css
--brand: #1f6feb;   /* primary blue */
--accent: #ff8a3d;  /* orange accent */
```

## Make the contact forms actually send to you

Right now the forms show a success message but **don't deliver anywhere** (it's a
front-end demo). To receive real submissions without running a server, use a free
form service. Easiest option — [Formspree](https://formspree.io):

1. Create a free Formspree account and get your form endpoint URL.
2. In `index.html`, change each `<form class="lead-form" ...>` to:
   ```html
   <form class="lead-form" action="https://formspree.io/f/yourID" method="POST">
   ```
3. In `script.js`, remove (or comment out) the `e.preventDefault()` line in the
   submit handler so the browser actually submits the form.

Other options: **Netlify Forms** (add `netlify` to the `<form>` tag if hosting on
Netlify), Google Forms, or your own backend.

## Publish it online (free options)

- **Netlify / Vercel / Cloudflare Pages** — drag-and-drop the `website` folder, or
  connect this repo. Free custom-domain support.
- **GitHub Pages** — push to GitHub, enable Pages in repo settings, point it at
  this folder.

---

Built as a starting point — tell me what AB Rentals rents and your real details,
and I can tailor the copy, sections, and branding exactly to your business.
