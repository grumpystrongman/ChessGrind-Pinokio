# Character portrait packaging (November 20, 2026)

The full ChessGrind release now includes **27 distinct, high-quality painterly WebP portraits** tracked in Git: 22 named rival bots and 5 authored coaches. The older local-only PNG images were not in Git, which caused all portrait requests to fail after Pinokio sync. The home dashboard independently hard-coded the older illustrated SVG coach images.

**Both defects are fixed:** the portrait binaries are committed to the repository and the dashboard, roster, coach gallery, game view, and player-vs-coach view reference `/icons/portraits/<id>.webp`. The server serves WebP with the correct MIME type and retains PNG handling for backward compatibility. Custom coaches not in the authored cast continue to use an SVG fallback.

The 27 characters each have a different actual image, including distinct Coach Morgan and Coach Quinn art. The release tests verify WebP signatures, non-empty files, no byte-for-byte duplicates, and correct references. A fresh Pinokio install or update now brings the images along with the code; no manual downloads or temporary files are required.

A browser refresh may be necessary after relaunch, but the changed .webp URLs avoid existing stale SVG browser caches.
