---
name: Siftlane Cloud Blue Console
description: A precise, light operations console for inspectable crawler workflows.
colors:
  brand: "#0052d9"
  brand-hover: "#003eb3"
  brand-soft: "#e8f2ff"
  app-background: "#f2f5f8"
  canvas: "#f5f9fd"
  surface: "#ffffff"
  surface-subtle: "#f8fafc"
  text: "#1b2b42"
  text-muted: "#60748b"
  line: "#dce4ec"
  line-strong: "#bac7d5"
  success: "#007a52"
  success-soft: "#e8f8f2"
  warning: "#c45f18"
  warning-soft: "#fff6e8"
  danger: "#c93535"
  danger-soft: "#fff0ed"
typography:
  headline:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif'
    fontSize: "19px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "0"
  title:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif'
    fontSize: "13px"
    fontWeight: 700
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
  sm: "4px"
  md: "6px"
  toggle: "9px"
  circle: "50%"
spacing:
  tight: "4px"
  compact: "8px"
  control: "12px"
  section: "16px"
  view: "20px"
components:
  button-primary:
    backgroundColor: "{colors.brand}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "34px"
  button-primary-hover:
    backgroundColor: "{colors.brand-hover}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "34px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "34px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.mono}"
    rounded: "{rounded.sm}"
    padding: "0 9px"
    height: "32px"
  workflow-node:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    width: "188px"
    height: "104px"
  status-badge-success:
    backgroundColor: "{colors.success-soft}"
    textColor: "{colors.success}"
    typography: "{typography.label}"
    rounded: "{rounded.xs}"
    height: "22px"
---

# Design System: Siftlane Cloud Blue Console

## Overview

**Creative North Star: "The Live Execution Lane"**

Siftlane is a calm, exacting control room organized around the execution path itself. The pale-blue workflow field is the visual center of gravity; cool-white rails, compact controls, and fine separators keep configuration and operational evidence close without turning the screen into a dashboard of detached cards.

The system is deliberately light, dense, and inspectable. Blue carries action, selection, focus, active paths, and live informational state. Semantic green, amber, and red remain independent so operators can distinguish success, caution, and failure without relying on position or memory. The Siftlane lane mark and name remain visible in the first viewport and establish an identity independent of any host product.

**Key Characteristics:**

- Continuous control-room composition rather than a collection of floating panels.
- A pale-blue dotted graph field framed by cool-white operational rails.
- Compact square controls, crisp 1px borders, and radii no larger than 6px for overlays.
- Written state labels, icons, and color used together.
- Monospace reserved for identifiers, selectors, timestamps, event types, and code values.

## Colors

The palette is cool, bright, and operational: one cloud-blue action family, restrained blue-gray neutrals, and clearly separated semantic states.

### Primary

- **Console Blue** (`brand`): Primary actions, active tabs, focused controls, selected paths, live events, and the lane mark.
- **Deep Console Blue** (`brand-hover`): Hover state for filled primary actions.
- **Selection Blue** (`brand-soft`): Selected rows, node-type tiles, compact badges, and informative highlights.

### Secondary

- **Execution Green** (`success` / `success-soft`): Completed nodes, healthy engine state, successful runs, and success badges.
- **Policy Amber** (`warning` / `warning-soft`): Policy notes, cancelling state, and warning events.
- **Failure Red** (`danger` / `danger-soft`): Failed or disconnected state, validation errors, destructive actions, and error surfaces.

### Neutral

- **Cool Application Ground** (`app-background`): The shell behind working surfaces.
- **Graph Mist** (`canvas`): The dominant workflow field.
- **Console White** (`surface`): Rails, bars, controls, tables, nodes, dialogs, and drawers.
- **Subtle Console White** (`surface-subtle`): Search and low-emphasis control fills.
- **Ink Blue** (`text`): Primary labels and operational content.
- **Telemetry Gray** (`text-muted`): Secondary labels, metadata, and inactive states.
- **Hairline Blue Gray** (`line`): Default separators and table rules.
- **Control Blue Gray** (`line-strong`): Input, control, and floating-panel boundaries.

**The One Operational Blue Rule.** Blue may identify action or live information, but it must not absorb success, warning, or failure semantics.

**The Written State Rule.** Every semantic color is paired with a readable label, icon, or status text; color is never the only signal.

## Typography

**Display Font:** None; this system has no hero typography.

**Body Font:** Native system UI sans with Segoe UI, PingFang SC, and Microsoft YaHei fallbacks.

**Label/Mono Font:** SFMono-Regular with Consolas and Liberation Mono fallbacks.

**Character:** Compact, familiar, and machine-adjacent without making the whole product look like a code editor. UI sans carries actions and explanations; mono gives durable technical values a distinct scanning rhythm.

### Hierarchy

- **Headline** (700, 19px, 1.25): Results headings; the canvas flow title may rise to 21px and compresses to 17px on narrow screens.
- **Title** (700, 13px): Rail, inspector, and dialog headings.
- **Body** (400, 11px): Buttons, list names, breadcrumbs, and explanatory text.
- **Label** (600, 10px): Tabs, field labels, statuses, table headers, and compact operational metadata.
- **Mono** (400, 10px): Node IDs, revisions, timestamps, event types, selectors, URLs, and schema-backed field values.

**The No Hero Type Rule.** Operate surfaces use compact hierarchy; do not import marketing-scale headings into the console.

**The Technical Value Rule.** Use monospace for values an operator may compare or copy, not for ordinary navigation or prose.

## Layout

The desktop shell fills `100dvh` and never scrolls at the document level. At full width it uses a 60px top bar, a 62px status strip, and a three-column work area: a 232px flow rail, a flexible center with a 560px minimum, and a 320px inspector. The center stacks a 46px workspace bar, the flexible content view, and a fixed 108px two-line event dock. Results and run history replace only the central content view; the surrounding operational context stays fixed.

At 1180px, the side rails compact to 210px and 288px and the center minimum becomes 520px. At 900px and below, the shell becomes one column: the flow rail and inspector become edge drawers, breadcrumbs and secondary desktop actions disappear, status statistics collapse, and the minimap is removed. At 560px and below, the workspace bar becomes 44px, the event dock becomes 94px, text commands collapse to familiar icons, and event lines retain the message while hiding timestamp and type. The graph itself remains full scale and pannable; nodes do not shrink into illegibility.

Spacing is intentionally dense and locally tuned around a compact 4/8/12/16/20px rhythm. Fixed dimensions keep toolbars, nodes, event rows, icon controls, and status counters stable as data changes.

**The Continuous Workspace Rule.** Rails, canvas, results, and live evidence belong to one full-height shell; do not recast each region as a floating card.

**The Preserve-the-Graph Rule.** On narrow screens, collapse chrome into drawers and icon controls while preserving node scale and canvas interaction.

## Elevation & Depth

The system is flat by default. Tonal layering and 1px borders establish the shell, while low ambient shadows are reserved for graph nodes and controls. Stronger directional shadows appear only where a layer must detach from the workspace: node library, anchored event ledger, drawer, toast, or modal. There are no decorative shadows on ordinary sections.

### Shadow Vocabulary

- **Graph lift** (`0 3px 10px rgba(49, 73, 104, 0.07)`): Workflow nodes at rest.
- **Floating control** (`0 3px 10px rgba(49, 73, 104, 0.08)`): React Flow controls and minimap.
- **Floating panel** (`0 14px 38px rgba(27, 43, 66, 0.18)`): Node library and mobile rail separation.
- **Anchored ledger** (`0 -16px 38px rgba(27, 43, 66, 0.16)`): Complete event history disclosed upward from the live dock.
- **Modal lift** (`0 22px 64px rgba(27, 43, 66, 0.25)`): Blocking dialogs only.

**The Flat-by-Default Rule.** A shadow must explain layering or interaction; it must never decorate a static content section.

**The Anchored Disclosure Rule.** The complete event ledger rises from its dock without moving the canvas, rails, or operator's working position.

## Shapes

The form language is rectangular and compact. Most controls, nodes, rows, notes, and table containers use gently squared 4px corners; tiny badges and icon tiles use 3px; dialogs and floating libraries may use 6px. Circular geometry is limited to status dots, connection handles, and switch thumbs. Borders are generally 1px; a selected or running node uses a 2px Console Blue boundary.

**The Compact Corner Rule.** Ordinary console surfaces stop at 4px and floating overlays stop at 6px; avoid pill-shaped labels and soft card silhouettes.

## Components

### Buttons

- **Shape:** Compact rectangular controls with gently squared corners (4px); standard height is 34px and workspace commands may compact to 30px.
- **Primary:** Console Blue fill, Console White label, 12px horizontal padding, 600 weight.
- **Hover / Focus:** Filled actions deepen to Deep Console Blue. Secondary controls move to a pale-blue surface with blue text and border. Keyboard focus is a 2px Console Blue outline with a 2px offset.
- **Secondary / Icon:** White fill and Control Blue Gray border. Icon-only controls remain stable squares, use Lucide symbols, and always carry an accessible name or tooltip.
- **Disabled:** Preserve geometry and reduce opacity to 48%; use a not-allowed cursor.

### Chips

- **Style:** Status badges are compact 22px-high rectangles with 3px corners and written labels.
- **State:** Live and queued use Selection Blue; success, warning, and failure use their own semantic soft/strong pairs.

### Cards / Containers

- **Corner Style:** Siftlane does not use generic dashboard cards. Workflow nodes are the signature framed object and use 4px corners.
- **Background:** Console White over Graph Mist.
- **Shadow Strategy:** Low graph lift only; see Elevation & Depth.
- **Border:** 1px cool-blue boundary at rest; 2px Console Blue when selected or running; semantic red on failure.
- **Internal Padding:** A 30px technical header followed by compact 9-12px content in a fixed 188x104px frame.

### Inputs / Fields

- **Style:** Console White fill, 1px Control Blue Gray border, 4px corners, and 10px monospace values; standard single-line height is 32px.
- **Focus:** Console Blue border plus a restrained 2px translucent blue halo.
- **Error / Disabled:** Error changes the boundary and message to Failure Red. Disabled fields use a cool gray fill and muted value while preserving contrast.

### Navigation

The top bar, flow rail, workspace tabs, and inspector are continuous white rails separated by hairlines. Active tabs use Console Blue text and a 2px underline. Selected flows use Selection Blue plus a visible border. At 900px the flow rail and inspector become left and right drawers behind explicit menu and panel controls; a neutral scrim communicates modality.

### Live Activity Dock

The persistent dock shows at most two recent events, a readable connection or run state, and a compact disclosure control. The full ordered ledger is an anchored overlay with sequence, message, type, and time columns; warning and error messages use semantic color while preserving their text.

### Results Table

Results use a bordered, scrollable table with a sticky cool-gray header and a 760px content minimum. Rows use pale-blue hover/selection, technical values remain compact, and long URLs or descriptions truncate rather than resizing the shell.

## Do's and Don'ts

### Do:

- **Do** keep the workflow canvas dominant and preserve the flow rail, engine state, inspector context, and two live activity lines around it.
- **Do** use Console Blue for action, focus, selection, active paths, and live information, with semantic colors reserved for their stated meanings.
- **Do** pair status color with text or icons and maintain visible keyboard focus.
- **Do** preserve full-scale pannable nodes on mobile while moving side rails into drawers.
- **Do** use the Siftlane lane mark, product name, and Cloud Blue Console vocabulary as the first-viewport identity.

### Don't:

- **Don't** import SubtleSight colors, components, navigation, logo, dark shell, AI-assistant styling, or document-editor patterns.
- **Don't** convert the console into bento cards, oversized metrics, a marketing hero, nested cards, decorative gradients, glass effects, or rounded pills.
- **Don't** hide the complete event record or expand it in a way that moves the operator's canvas position.
- **Don't** imply unshipped browser automation, authenticated platform adapters, or arbitrary Python/JavaScript execution through labels, icons, or example states.
- **Don't** make success, warning, failure, or cancellation blue.
