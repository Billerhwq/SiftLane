---
name: SiftLane Lane Studio
description: A quiet, inspectable automation studio for building crawlers and reading their captured evidence.
colors:
  primary: "#3568c8"
  primary-hover: "#28539f"
  primary-soft: "#edf3ff"
  canvas: "#f7f9fc"
  surface: "#ffffff"
  surface-subtle: "#f6f8fa"
  text: "#202124"
  text-muted: "#667085"
  line: "#e2e6eb"
  line-strong: "#c9d0d9"
  success: "#2f7a44"
  success-soft: "#eaf6ed"
  warning: "#ad6516"
  warning-soft: "#fff5df"
  danger: "#be4c45"
  danger-soft: "#fff0ee"
  accent-sun: "#f0cc68"
  accent-coral: "#eaa39d"
  accent-mint: "#78bf95"
  accent-violet: "#4632a5"
typography:
  headline:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif'
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "0"
  reading:
    fontFamily: '"Source Han Serif SC", "Noto Serif CJK SC", "Songti SC", serif'
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.95
    letterSpacing: "0"
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif'
    fontSize: "11px"
    fontWeight: 400
    letterSpacing: "0"
  label:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif'
    fontSize: "10px"
    fontWeight: 600
    letterSpacing: "0"
  mono:
    fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", monospace'
    fontSize: "10px"
    fontWeight: 400
    letterSpacing: "0"
rounded:
  xs: "3px"
  sm: "6px"
  md: "7px"
  lg: "8px"
  circle: "50%"
spacing:
  tight: "4px"
  compact: "8px"
  control: "12px"
  section: "16px"
  view: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "34px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "34px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "34px"
  icon-button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-muted}"
    rounded: "{rounded.md}"
    width: "34px"
    height: "34px"
  utility-action:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.text-muted}"
    rounded: "{rounded.circle}"
    width: "40px"
    height: "40px"
  input:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.text}"
    typography: "{typography.mono}"
    rounded: "{rounded.sm}"
    padding: "0 9px"
    height: "32px"
  workflow-node:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    width: "196px"
    height: "110px"
  result-row:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    height: "52px"
---

# Design System: SiftLane Lane Studio

## Overview

**Creative North Star: "The Clear Automation Workbench"**

Lane Studio is a quiet desktop workbench where operators build a crawl as a visible sequence, watch execution evidence, and move directly from captured rows into readable source detail. It combines a pale technical canvas with a full-viewport white application shell, precise dividers, and small moments of sun, coral, mint, and violet so different node roles remain recognizable without turning the product into a one-hue console.

The design is dense but not cramped. Navigation and status stay fixed around the work, the graph remains the visual center, and details replace the center surface instead of appearing in a drawer or modal. The edge-to-edge shell feels like a purpose-built local application rather than a dashboard assembled from cards.

**Key Characteristics:**

- One full-viewport, continuous studio with a 64px utility rail, 248px flow rail, flexible workspace, and 316px inspector.
- A restrained neutral foundation with blue for action and distinct semantic and node-role accents.
- Compact controls, 6-8px corners, stable dimensions, and no nested dashboard cards.
- System sans for operation, monospace for inspectable values, and a Chinese serif stack for captured article reading.
- Purposeful surface transitions that disappear when reduced motion is requested.

## Colors

The palette is light, neutral, and tool-like, with one dependable action blue and a small set of warm and cool accents for orientation.

### Primary

- **Lane Blue** (`primary`): Primary commands, selected navigation, focus, active graph state, and links.
- **Deep Lane Blue** (`primary-hover`): Hover and pressed treatment for filled actions.
- **Selection Wash** (`primary-soft`): Selected flows, active utilities, node-role tiles, and table-row emphasis.

### Secondary

- **Completion Green** (`success` / `success-soft`): Healthy engine state, completed work, enabled state, and the start-node family.
- **Attention Amber** (`warning` / `warning-soft`): Policy and caution states.
- **Failure Coral** (`danger` / `danger-soft`): Failures, invalid fields, destructive actions, and error surfaces.

### Tertiary

- **Connection Sun** (`accent-sun`): Sparse structural highlights in the empty-workflow illustration.
- **Activity Coral** (`accent-coral`): Current activity and selected content cues.
- **Evidence Mint** (`accent-mint`): Live evidence dots, article provenance, and positive flow accents.
- **Identity Violet** (`accent-violet`): User identity only; never a general action color.

### Neutral

- **Working Canvas** (`canvas`): Graph and low-emphasis data backgrounds.
- **Paper Surface** (`surface`): Bars, rails, nodes, tables, and the article document.
- **Quiet Surface** (`surface-subtle`): Search, metadata, and secondary control fills.
- **Graphite Text** (`text`): Primary content and labels.
- **Measured Gray** (`text-muted`): Secondary copy and technical context.
- **Hairline** (`line`): Section, row, and shell dividers.
- **Control Line** (`line-strong`): Input and control boundaries.

**The Semantic Independence Rule.** Blue communicates action and selection; green, amber, and coral keep their own operational meanings.

**The Accent Restraint Rule.** Sun, coral, mint, and violet identify roles or moments. They do not become broad background themes.

## Typography

**Display Font:** None; Lane Studio has no marketing or hero scale.

**Body Font:** Native system UI sans with Segoe UI, PingFang SC, and Microsoft YaHei fallbacks.

**Reading Font:** Source Han Serif SC with Noto Serif CJK SC and Songti SC fallbacks.

**Label/Mono Font:** SFMono-Regular with Consolas and Liberation Mono fallbacks.

**Character:** Operational text remains familiar and compact, technical identifiers remain easy to compare, and captured articles switch to a calmer editorial rhythm without changing the application shell.

### Hierarchy

- **Headline** (700, 20px, 1.25): Workspace and empty-state titles; article titles use the reading stack at 30px and 1.45.
- **Title** (600-700, 12-16px): Brand, rail, inspector, and data-view titles.
- **Reading** (400, 15px, 1.95): Article body copy in the independent detail view, capped by the 760px document column.
- **Body** (400, 11px): Navigation, actions, list rows, explanations, and table content.
- **Label** (600, 9-10px): Status, fields, tabs, metadata, and table headers.
- **Mono** (400, 9-10px): IDs, URLs, selectors, timestamps, counts, and serialized metadata.

**The No Hero Type Rule.** This is an operate-first product; headings stay proportional to the surrounding tool surface.

**The Reading Shift Rule.** Serif appears only when the user enters captured article content. Controls, metadata, and surrounding navigation remain sans or mono.

## Layout

Desktop uses an edge-to-edge `100dvh` shell with no outer margin, a 62px top bar, and a 44px status row. Below those rows, four stable tracks organize the application: a 64px utility rail, a 248px flow rail, a flexible workspace with a 580px minimum, and a 316px inspector. The workspace stacks a 52px view bar, flexible canvas/result/detail content, and a 96px live event dock.

The graph and result table occupy the same central surface. Selecting a result replaces that surface with the independent article detail view; it never opens a drawer or dialog. The detail view uses a flexible reading document plus a 264px facts column, with a sticky 54px action bar.

At 1280px, the shell compacts to 60/220/flexible/288px. At 960px, flow and inspector rails become explicit edge panels while the utility rail remains. At 680px, the utility rail disappears, the shell becomes a single-column full viewport, and detail controls expand to at least 44px. Detail mode also compresses top/status/workspace chrome so the article owns the available height.

Spacing follows a practical 4/8/12/16/24px rhythm. Fixed heights and grid tracks prevent statuses, loading text, buttons, nodes, and table content from shifting the shell.

**The Continuous Studio Rule.** Navigation, graph, evidence, results, and details belong to one application frame, not a collection of floating cards.

**The Replace-the-Center Rule.** Canvas, results, history, and article detail are peer views that replace the center region while preserving operational context.

## Elevation & Depth

The system uses tonal layering and hairline borders by default. The application shell stays flat against the browser viewport. Workflow nodes use a low work-surface shadow; selected nodes gain a blue-tinted lift. Strong shadows are reserved for temporary layers such as the node library, event ledger, edge panel, toast, and dialog.

### Shadow Vocabulary

- **Node rest** (`0 7px 20px rgba(51, 67, 88, .1)`): Workflow nodes at rest.
- **Node active** (`0 11px 28px rgba(53, 104, 200, .18)`): Selected and running nodes.
- **Floating layer** (`0 16px 46px rgba(35, 49, 68, .16)`): Temporary libraries, dialogs, and drawers.
- **Anchored ledger** (`0 -18px 48px rgba(35, 49, 68, .18)`): The event record disclosed upward from its dock.

**The Full Viewport Rule.** The application shell reaches every browser edge; ordinary sections inside it remain flat and connected.

**The Functional Depth Rule.** Strong elevation must identify a temporary or selected layer, never decorate static content.

## Shapes

Lane Studio uses softly squared geometry. Inputs use 6px corners, core controls and nodes use 7px, and shell or temporary surfaces use 8px. Circular form is reserved for utility-rail actions, status dots, connection handles, and user identity. Result rows and document regions remain rectangular and are separated by hairlines.

**The Small Radius Rule.** Repeated operational surfaces stay at 8px or below; do not introduce oversized soft cards or pills.

## Components

### Buttons

- **Shape:** Stable 34px controls with 7px corners; the top-level run action may use 38px height.
- **Primary:** Lane Blue fill, white label, and 12-15px horizontal padding.
- **Hover / Focus:** Primary actions deepen to Deep Lane Blue. Secondary and icon controls receive Selection Wash and blue text. Keyboard focus uses a 2px Lane Blue outline with a 2px offset.
- **Icon:** Use Lucide symbols in stable squares and provide an accessible name or native tooltip.
- **Mobile detail:** Back, previous, next, original-source, and event controls expand to at least 44px.

### Utility Rail

- **Style:** A 64px neutral rail with 40px circular icon actions and a 6px vertical rhythm.
- **State:** Selected tools receive Selection Wash plus a 3px left Lane Blue marker.

### Workflow Nodes

- **Shape:** Fixed 196x110px white nodes with 7px corners and a 32px technical header.
- **Role color:** Start, HTTP, extraction, branching, and emit roles use different restrained icon-tile colors while the node body stays neutral.
- **State:** Running or selected uses a 2px Lane Blue edge and active lift; completion and failure retain independent semantic colors.

### Inputs / Fields

- **Style:** Quiet Surface fill, 1px Control Line, 6px corners, and monospace values at a stable 32px single-line height.
- **Focus:** White fill, Lane Blue boundary, and a restrained 3px translucent halo.
- **Error / Disabled:** Failure Coral boundary and message for errors; muted fill and readable reduced emphasis for disabled fields.

### Results Table

- **Style:** One 7px framed table surface with a 40px sticky header and stable 52px rows.
- **Interaction:** Rows are pointer and keyboard targets. Hover and selection use a pale blue surface without changing row height.
- **Transition:** Activating a row switches the workspace to the independent detail panel and preserves the row for focus restoration.

### Article Detail

- **Structure:** Sticky action bar, centered paper document, and a separate 264px provenance column.
- **Reading:** Title and body use the serif reading stack; metadata, IDs, and controls preserve the studio's compact operational typography.
- **Navigation:** Back, previous, next, and open-original actions are always available. Escape returns to results, arrow keys traverse items, and the result row regains focus on return.

### Navigation

The top bar, utility rail, flow rail, workspace tabs, and inspector form one continuous shell. Selected tabs use Lane Blue text and a 3px baseline. At 960px the flow rail and inspector become edge panels behind explicit controls; at 680px the utility rail is removed and the top bar carries the essential commands.

## Do's and Don'ts

### Do:

- **Do** keep the graph or currently selected evidence as the dominant center surface.
- **Do** preserve the 64/248/flexible/316 desktop structure and its documented responsive collapses.
- **Do** use role accents sparingly and always keep status meaning readable in text.
- **Do** treat article detail as a full center view with reading typography, metadata, keyboard navigation, and focus restoration.
- **Do** keep operational controls compact on desktop and at least 44px in mobile detail mode.

### Don't:

- **Don't** open captured item detail in a drawer, modal, or dialog.
- **Don't** convert the studio into a bento dashboard, nested cards, a marketing hero, or a decorative gradient field.
- **Don't** make every node and status blue; preserve role and semantic distinctions.
- **Don't** scale graph nodes down for mobile; collapse surrounding chrome and keep the work readable.
- **Don't** use the reading serif for navigation, form controls, status, or metadata.
