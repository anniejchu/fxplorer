# Frontend

Primary setup and run instructions live in the repository [README](../README.md).

Local dev command:

```bash
npm run dev -- --host 0.0.0.0 --port 5173
```

Vite proxies the same-origin `/api` path to the backend at `127.0.0.1:5000`.
