# Production Startup And EXE Packaging

This project keeps the development startup path unchanged and adds a separate
production path for packaged Windows runs.

## Development

The existing commands still work:

```powershell
er --port 8892
cd web
npm run dev
```

In this mode FastAPI remains API-only. Vite serves the Vue app.

## Production Without Packaging

Build the frontend once:

```powershell
cd web
npm run build
```

Then start the production entry:

```powershell
er-production --port 8892
```

The production entry mounts `web/dist` as a Vue SPA, opens the browser, and
uses the project root for `.env`, `data/`, `result/`, and `logs/`.

Useful overrides:

```powershell
er-production --project-root D:\ElectronicRecognition --web-dist D:\ElectronicRecognition\web_dist
```

Environment overrides are also supported:

```powershell
$env:ER_PROJECT_ROOT = "D:\ElectronicRecognition"
$env:ER_WEB_DIST = "D:\ElectronicRecognition\web_dist"
er-production
```

## Build EXE

Install build dependencies if needed:

```powershell
python -m pip install -e ".[build]"
```

Build the release folder:

```powershell
.\scripts\build_exe.ps1
```

The output is:

```text
dist\ElectronicRecognition\ElectronicRecognition.exe
```

The script builds the frontend, runs PyInstaller, and prepares:

```text
dist\ElectronicRecognition\
  ElectronicRecognition.exe
  web_dist\
  data\
  result\
  logs\
  .env
```

Large local embedding models are not copied by default. To include
`data\models`, run:

```powershell
.\scripts\build_exe.ps1 -CopyModels
```

CATIA and AutoCAD are not bundled. CATDrawing and DWG export still require the
target Windows machine to have the relevant software installed and COM
registered.
