# Design Direction: hermes-kleinanzeigen Documentation & Showcase Site

## Identity & Tone
- **Domain**: Developer tooling, open-source agent integration, German classifieds monitoring.
- **Brand Character**: Utilitarian, engineering-focused, fast, precise. Clean technical documentation meets an interactive command & filter generator.
- **Tone**: Pragmatic and honest. Zero buzzwords, zero inflated statistics, zero fake reviews or artificial badges.

## Dials (Antislop Part 3)
- **ENERGY: 1 (Calm)**: Clean, high-legibility interface, clear semantic hierarchy, zero neon glows or floating mesh blobs.
- **RHYTHM: 2 (Balanced)**: Structured flow (Header -> Hero with terminal & quick copy -> Interactive Query Generator -> Dual Architecture Breakdown -> Live-like Inspection & Schema -> Installation Matrix -> Footer).
- **MOTION: 1 (Calm / Functional)**: Interactive state changes, smooth tab switching, copy-to-clipboard transitions, theme toggle fade. All animations strictly respect `prefers-reduced-motion`.

## Color Palette (WCAG AA Compliant)
- **Primary / Canvas**:
  - Dark mode: `#0c0f14` (Deep obsidian background), `#141822` (Card surface), `#232a3b` (Borders/dividers).
  - Light mode: `#f8fafc` (Slate light background), `#ffffff` (Card surface), `#cbd5e1` (Borders).
- **Brand Accent**:
  - `#10b981` / `#059669` (Terminal emerald, reminiscent of Kleinanzeigen green / agent terminal verification).
  - Secondary neutral accent: `#38bdf8` / `#0284c7` (Hermes cyan for tools/identifiers).
- **Text**:
  - Dark: `#f1f5f9` (Primary text, 15:1 contrast), `#94a3b8` (Muted text, 5.8:1 contrast).
  - Light: `#0f172a` (Primary text, 16:1 contrast), `#475569` (Muted text, 6.2:1 contrast).

## Typography
- **Headings & Body**: System sans-serif stack (`system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`) for crisp native rendering across OSes.
- **Code & Terminals**: Monospace stack (`ui-monospace, 'Cascadia Code', 'Fira Code', Menlo, Consolas, monospace`).

## Interactive Features
1. **Interactive Query & URL Builder**: Select keyword, PLZ, radius, price range, and see the exact canonical Kleinanzeigen URL generated in real-time alongside equivalent Hermes Agent tool call and CLI command.
2. **Tabbed Architecture Visualizer**: Compare Hermes Plugin (Native Tools) vs Standalone Skill (CLI / Subprocess) workflows side-by-side with genuine technical pros and cons.
3. **One-click Copy & Notification Feedback**: Real copy action using Clipboard API with keyboard accessibility and toast feedback.
4. **Theme Switcher**: Fully functional Light / Dark mode toggle with `localStorage` persistence and system preference detection.
