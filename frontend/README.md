# Prometheus Frontend (Next.js 14)

Step 4.1 shell: Firebase Auth login, authenticated layout (sidebar + header + theme),
the global URL-synced filter bar, the "data as of" freshness banner, a typed API
client, and TanStack Query. No charts yet.

## Local development

```bash
cd frontend
npm install
cp .env.example .env.local   # fill in Firebase web config + API base URL
npm run dev                  # http://localhost:3000
```

## Quality gates

```bash
npm run lint        # eslint (next/core-web-vitals)
npx tsc --noEmit    # TypeScript strict
npm run build       # production build
```

## Notes

- All settings are `NEXT_PUBLIC_*` (Firebase web config is not secret). Never commit `.env.local`.
- The API client attaches the Firebase ID token and unwraps the backend error
  envelope (`{"error": {"code", "message"}}`) into an `ApiError`.
- Filter state (date range/compare/platform/pods/publishers/apps) lives entirely in
  the URL search params, so views are shareable and back/forward works.
- Pod/publisher/app filter options are populated from `/api/v1/apps`; the banner
  reads `/api/v1/meta/freshness`.
- Dark/light theme via `next-themes`; shadcn/ui-style components under `components/ui`.
