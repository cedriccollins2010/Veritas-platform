# VERITAS — Frontend

Interface Next.js 16 (App Router, React 19, TypeScript, Tailwind CSS 4).

```bash
npm install
npm run dev          # http://localhost:3000
npm run lint
npm run typecheck    # génère les types de routes puis lance tsc
npm run build
```

`API_INTERNAL_URL` (par défaut `http://localhost:8000`) indique au serveur Next.js où joindre l'API.

Avant de modifier du code Next.js, lire `AGENTS.md` : cette version introduit des changements importants (Cache Components, `connection()`, types de routes générés).
