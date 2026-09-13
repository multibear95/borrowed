<div align="center">

<img src="assets/logo.png" alt="MORE logo" width="120">

# MORE

### More than once.

**A peer-to-peer platform for occasion wear with more life left to live.**

**[✨ Open the visual landing page](https://multibear95.github.io/borrowed/demo/)**

<p>
  <img alt="Next.js 15" src="https://img.shields.io/badge/Next.js-15-000000?logo=nextdotjs&logoColor=white">
  <img alt="React 19" src="https://img.shields.io/badge/React-19-087EA4?logo=react&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-Python%203.12-009688?logo=fastapi&logoColor=white">
  <img alt="OpenAI Responses API" src="https://img.shields.io/badge/OpenAI-Responses%20API-412991?logo=openai&logoColor=white">
  <img alt="Railway" src="https://img.shields.io/badge/Railway-deployed-0B0D0E?logo=railway&logoColor=white">
  <img alt="Licence MIT" src="https://img.shields.io/badge/licence-MIT-A0522D">
</p>

<p>
  <a href="#-the-idea">The idea</a> ·
  <a href="#-landing-page">Landing page</a> ·
  <a href="#-see-it-in-action">Demo video</a> ·
  <a href="#-how-it-feels">How it feels</a> ·
  <a href="#-what-the-ai-decides--and-what-it-does-not">What the AI decides</a> ·
  <a href="#-under-the-hood">Under the hood</a> ·
  <a href="#-the-team">Team</a> ·
  <a href="DEVELOPMENT.md">Run it yourself</a>
</p>

<sub>Built in 24 hours at the <b>AI.WOMEN Hackathon</b> · Hamburg · 12–13 September 2026 🧵</sub>

</div>

---

## ✨ The idea

We already have more than we think: more clothes in our wardrobes, more
occasions ahead, and more beautiful pieces that deserve another life. Yet when
we need something for an event, the default is still to buy something new.

MORE offers another way: **more to wear, give and share — more than once.** A
dress bought for one celebration can move to another woman, another city and
another unforgettable night. The goal is not to ask women to want less; it is to
create smarter ways to have more possibilities — with less waste and less
consumption.

Occasion wear is a particularly good place to start. It is often bought for one
fixed date, worn once, and then left hanging in the dark for years. Renting
extends the value of that piece and gives the next wearer something special
without another purchase.

> One dress. Many nights. Many women.

## ✨ Landing page

The visual introduction to MORE is available as a standalone, static page:
[open the landing page](https://multibear95.github.io/borrowed/demo/). Its
[source lives in the repository](docs/demo/index.html), together with the three
catalogue images it uses.

## 🎬 See it in action

<div align="center">

<a href="assets/demo.mp4"><img src="assets/demo-poster.png" alt="Watch the MORE demo" width="720"></a>

<sub><b><a href="assets/demo.mp4">▶︎ Watch the 33-second walkthrough</a></b> — from "I need a red dress for my
birthday party" to a confirmed reservation.</sub>

</div>

## 👗 How it feels

No filters. No twelve-step forms. You just say what is happening in your life:

> **You:** I have a wedding in Sicily in September. I am looking for a chic mini
> dress with a trendy colour or print.

The assistant asks only for what it still genuinely needs in order to run a
reliable availability check. When the city, date or size is missing, it shows one
interactive card where you can:

- 📅 pick a wear date
- 📍 pick a city from the catalogue
- 📏 select an EU size
- 🥂 optionally add the occasion — gala, wedding, party
- ✅ send everything with a single click

Then up to **three** garments come back — and only garments that can actually
reach you in time:

<div align="center">
  <img src="assets/card-selezza.png" alt="Result card: Selezza Powder Dress by Opulence, €80 for 4 days, lands Thu 17 Sept" width="250">
  &nbsp;&nbsp;
  <img src="assets/card-vesper.png" alt="Result card: Vesper Dress by Zuhair Murad, €320 for 4 days, lands Thu 17 Sept" width="250">
</div>

<div align="center">
  <sub>Every card carries the lender, the rating, the city, the price for the
  rental window — and the date it lands on your doorstep.</sub>
</div>

Each preview is checked for city, size, dates, shipping lead time, existing
bookings, return time and cleaning time **before** it is shown. A request for a
colour is treated as a filter, not merely a ranking preference. If a dress
cannot arrive before the wedding, you never see it.

Choose one, confirm, and the garment is held for you. The conversation keeps its
state while the session is open.

## 🧠 What the AI decides — and what it does not

| The model does | Deterministic backend code does |
| --- | --- |
| Extracts explicitly stated details from your message | Checks size, city and date feasibility |
| Identifies missing information and writes a short question | Computes shipping, return and cleaning windows |
| Interprets an optional event or colour preference | Rejects garments with conflicting bookings or insufficient delivery time |
| Summarises the three recommendations in English | Returns the exact cards shown in the interface |

The availability result **never** comes from the model. It is computed from the
catalogue and the request, so a garment that cannot arrive in time is never
presented as a recommendation. Pretty answers are not enough — the dress has to
show up.

## 🔧 Under the hood

```text
frontend/   Next.js 15 · React 19 · TypeScript · SSE chat
backend/    FastAPI · Pydantic · LangGraph · OpenAI Responses API
data/       386-item seed catalogue (250 dresses, 136 accessories)
```

Availability, ranking and reservations live in plain Python domain rules;
conversation state and bookings are kept in memory with JSON snapshots, so a
restart does not lose a hold.

👉 **Setup, environment variables, checks and architecture:
[DEVELOPMENT.md](DEVELOPMENT.md)**

## 🚧 Product boundaries

This is a hackathon prototype. It includes a real availability and reservation
flow, but no payment, user accounts, identity verification, insurance, courier
integration or booking cancellation. A reservation holds a garment; it does not
take money. The frontend is borrower-first — lender-facing work remains in the
repository but is not the active demo flow.

## 📦 Data

The 386-item demo catalogue is based on public data from
[DCEY](https://www.davetcokelbisemyok.com). Images belong to DCEY and are used
for hackathon demonstration only. Rental prices, availability, delivery lead
times, bookings and lender details are demo-domain data modelled by the team.

See [DATA.md](DATA.md) for the source, pipeline and known gaps. The architecture
and full product specification are in [ARCHITECTURE.md](ARCHITECTURE.md),
[SPEC.md](SPEC.md), [frontend spec](specs/FRONTEND_SPEC.md) and
[backend spec](specs/BACKEND_SPEC.md).

## 🛠 Built with

Next.js 15 · React 19 · FastAPI · Pydantic · LangGraph · OpenAI Responses API ·
Server-Sent Events · Railway · a lot of coffee ☕

## 💃 The team

<div align="center">

| Product | Development |
| :--- | :--- |
| [Gizem](https://www.linkedin.com/in/gizemisik/) · [Sonali](https://www.linkedin.com/in/sonali-jadhav444/) · [Neelamma](https://www.linkedin.com/in/neelamma-doddannavar/) | [Victoria](https://www.linkedin.com/in/victoria-streltsova/) · [Jing](https://www.linkedin.com/in/janewush/) |

</div>

## 📄 Licence

[MIT](LICENSE). The code is ours; the catalogue images are not — see
[Data](#-data).

<div align="center">
<sub><b>MORE</b> — because that dress deserves more than one night.</sub>
</div>
