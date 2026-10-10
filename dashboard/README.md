# AgriPulse-813 · Stage 5A

A local frontend by **Beyond The Limit**, built with Next.js, React, TypeScript,
Tailwind CSS, Framer Motion, react-globe.gl / Three.js, Lucide icons, and locally
bundled Geist fonts. Dependencies are pinned in `package-lock.json`.

## Install and run

Requires Node.js 20.9 or newer. From the repository root in PowerShell:

```powershell
Set-Location .\dashboard
npm.cmd ci
npm.cmd run dev
```

Open **http://127.0.0.1:3000**. Use `npm` instead of `npm.cmd` on macOS/Linux.
The Windows command avoids PowerShell's restricted `npm.ps1` wrapper.

For a production preview, stop the development server, then run from `dashboard/`:

```powershell
npm.cmd run build
npm.cmd start
```

## Current scope

- `/`: the AgriPulse-813 landing page, Earth globe, and **Launch Demo**.
- `/scene`: scene selection, smooth geographic focus, and **Open dashboard**.
- `/dashboard`: Farmer / Expert shells with navigable sections and a mode switch.
  Mode and section selection are preserved in URL query parameters.
- Konya, Turkey is the **current validated demo scene**. Syria and the Arab region
  are **target deployment only**, without validated analysis in this demo.
- Every analysis area is a labeled placeholder. No scientific values, sensor
  readings, field recommendations, or real Stage 1–4.5 outputs are displayed.
- The responsive dark interface includes keyboard navigation, reduced-motion
  support, and a usable scene-selection fallback when WebGL is unavailable.
- Fonts and [globe geography](public/globe/ATTRIBUTION.md) are served locally.
  The globe provides regional context, not scene coverage or satellite imagery.

## Deferred to Stage 5B

Loading and validating existing scientific JSON outputs; real maps, temporal and
spectral evidence views; decision traces; provenance and result-specific
limitations; and missing/incompatible-data states.

Stage 5A adds no API routes, custom backend, authentication, database, ML, IoT,
weather, ground-truth forms, irrigation controls, or additional product modes.
The scientific stages remain unchanged.
