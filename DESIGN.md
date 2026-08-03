---
name: SiftLane Operations Workspace
description: A compact desktop operations system for building, scheduling, running, and inspecting crawler workflows.
colors:
  primary: "#002fa7"
  primary-hover: "#00257f"
  primary-soft: "#eaf0ff"
  canvas: "#f4f6f9"
  surface: "#ffffff"
  surface-subtle: "#f7f8fa"
  text: "#172033"
  text-muted: "#657084"
  line: "#d9dde5"
  success: "#16865c"
  warning: "#b96d00"
  danger: "#c53b3f"
typography:
  headline:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif'
    fontSize: "18px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "0"
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif'
    fontSize: "12px"
    fontWeight: 400
    letterSpacing: "0"
  operational:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif'
    fontSize: "10px"
    fontWeight: 400
    letterSpacing: "0"
  reading:
    fontFamily: '"Source Han Serif SC", "Noto Serif CJK SC", "Songti SC", serif'
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.95
    letterSpacing: "0"
  mono:
    fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", monospace'
    fontSize: "10px"
    fontWeight: 400
    letterSpacing: "0"
rounded:
  xs: "4px"
  sm: "5px"
  md: "6px"
spacing:
  tight: "4px"
  compact: "8px"
  control: "12px"
  section: "18px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "34px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
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
    rounded: "{rounded.xs}"
    padding: "0 9px"
    height: "34px"
  navigation-item:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-muted}"
    rounded: "{rounded.xs}"
    height: "40px"
  schedule-table-row:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    height: "46px"
---

# Design System: SiftLane Operations Workspace

## Overview

**Creative North Star: "The Operational Railway"**

SiftLane is a continuous desktop control surface for defining workflows, scheduling them, following runs, and inspecting captured evidence. The interface is bright, compact, and divided by hairlines rather than decorative cards. Blue identifies action and selection; green, amber, and red retain independent operational meaning.

Task Scheduling is a first-class destination beside Workflow Editor, Run History, and Collection Results. Ant Design 6 owns management-interface behavior and visual grammar: menus, buttons, search and segmented filters, tables, forms, Drawer, confirmation, and tags. Lucide supplies interface icons. World Monitor owns only the scheduling overview's topology of a dominant situation field, collapsible peripheral Docks, bottom live-signal panels, and top-level view switching; its map aesthetic, dark theme, and visual styling are not part of SiftLane.

The shipped scheduling scope is defined by `documentation/PRD-SiftLane-Task-Scheduling-Center.md`.

**Key Characteristics:**

- Persistent left navigation with a clear selected state and a compact state at 1280px.
- Dense, flat, full-viewport desktop composition with stable rows and columns.
- Real operational data, explicit state labels, and restrained semantic color.
- Low-radius controls and surfaces (4-6px), 34px controls, and a 10px operational type floor.
- Separate but consistent center views for workflow editing, runs, results, article detail, and scheduling.

## Colors

The palette is neutral and work-focused, with SiftLane Blue reserved for commands, navigation, selection, focus, the current-time rule, and scheduled-fire markers.

### Primary

- **SiftLane Blue** (`primary`): Primary actions, selected navigation, links, focus, and active schedule markers.
- **Deep SiftLane Blue** (`primary-hover`): Hover and pressed state for filled actions.
- **Selection Blue** (`primary-soft`): Selected menu items, selected rows, and low-emphasis active surfaces.

### Secondary

- **Operational Green** (`success`): Enabled schedules, successful runs, and healthy live state.
- **Operational Amber** (`warning`): Queued or caution states.
- **Operational Red** (`danger`): Errors, failed runs, destructive actions, and validation failures.

### Neutral

- **Operations Canvas** (`canvas`): Application background and table header ground.
- **Paper Surface** (`surface`): Navigation, controls, tables, and primary work areas.
- **Quiet Surface** (`surface-subtle`): Secondary rails and subdued control regions.
- **Ink** (`text`): Primary content and identifiers.
- **Measured Gray** (`text-muted`): Supporting labels, timestamps, and context.
- **Hairline** (`line`): Shell, column, section, and row divisions.

**The Semantic Independence Rule.** Blue communicates action and selection; status meaning remains green, amber, or red and is always paired with text or an icon.

## Typography

**Display Font:** None; this is an operate-first product with no hero scale.

**Body Font:** Native system sans with Segoe UI, PingFang SC, and Microsoft YaHei fallbacks.

**Label/Mono Font:** SFMono-Regular with Consolas and Liberation Mono fallbacks for times, Cron expressions, IDs, counts, and machine values.

**Reading Font:** Source Han Serif SC with Noto Serif CJK SC and Songti SC fallbacks, used only for captured article content.

### Hierarchy

- **Page headline** (700, 18px, 1.25): Scheduling-center and principal workspace titles.
- **Ant Design base** (400, 12px): Standard controls and management content.
- **Operational minimum** (400-650, 10px): Dense table cells, rail rows, state strips, timestamps, and labels. Do not go below 10px.
- **Reading** (400, 15px, 1.95): Captured article body only.
- **Mono** (400, 10px): Cron, timezone, timestamps, counts, IDs, and serialized values.

**The No Hero Type Rule.** Headings stay proportional to the surrounding operating surface.

## Layout

The application fills the desktop viewport. A 56px top bar and 44px status strip frame a first-class left navigation rail. At 1440px the navigation is 188px wide; at 1280px it compacts to 64px while keeping all destinations available. These two desktop sizes, 1440x900 and 1280x800, are the validated scope of this redesign.

The workflow area separates discovery from composition. Flow Library is a full-width child module with search, a management table, and a capped recent-run signal deck. Opening a flow enters the flexible graph workspace; the settings inspector is a right Dock Drawer that independently collapses from 304px to a 44px labeled rail and persists the user's preference. Runs and results replace the central working surface without changing primary navigation. Selecting a result replaces the center with article detail; it does not open a Drawer or modal, and return restores the originating row context.

Scheduling uses a dedicated full-width workspace after the navigation rail. It stacks a 60px page header with four view tabs, a 44px six-part status strip, and a World Monitor-inspired situation field:

- Left Dock: searchable, segmented schedule filters and a capped upcoming roster.
- Center: a dominant exact now-to-plus-24-hour railway band above risk and execution-signal panels.
- Right Dock: selected schedule context above the related live run ledger.

At 1440px the expanded field is 220px / flexible center / 290px. Both Docks independently collapse to a stable 44px summary rail and persist their state; at 1280px the right Dock defaults collapsed on first use. Plans, runs, and exceptions move to separate full-width views reached through the header tabs. The overview caps peripheral feeds and provides explicit “view all” transitions instead of accumulating long lists.

**The Continuous Workspace Rule.** Navigation, status, working field, and context are one connected application surface, not a set of floating dashboard cards.

**The Desktop Scope Rule.** This redesign documents and accepts only 1440x900 and 1280x800 desktop Web behavior; it makes no mobile acceptance or capability claim.

## Elevation & Depth

Static structure is flat and separated with `line` hairlines and subtle tonal changes. Workflow nodes have a restrained work-surface shadow, with a blue-tinted lift for selected or running nodes. Strong elevation is reserved for temporary layers such as the Ant Design Drawer, dialogs, menus, and toasts.

**The Flat-at-Rest Rule.** Scheduling Docks, the horizon, signal deck, dedicated data tables, selected context, and live ledger do not use decorative elevation.

## Shapes

SiftLane uses softly squared geometry. Repeated controls and navigation items use 4-5px corners; temporary surfaces stop at 6px. Circular geometry is reserved for status dots, connection handles, user identity, and precise schedule-fire markers.

**The Low-Radius Rule.** Operational components remain within the 4-6px radius range; do not introduce oversized rounded cards or text pills.

## Components

### Navigation

- Ant Design Menu owns the primary navigation, including Workflow Editor, Run History, Collection Results, Task Scheduling, Connectors, and permission-dependent Team & Security.
- Items are 40px high with 4px corners. Selection uses `primary-soft`, `primary` text, and a 3px leading marker.
- At 1280px the menu becomes icon-led but retains tooltips and accessible names.

### Management Controls

- Ant Design 6 owns buttons, menus, search, segmented filters, tables, forms, Drawer, confirmation, and tags.
- Standard controls are 34px high. Primary controls use SiftLane Blue with no decorative shadow.
- Permission-aware actions remain visible but disabled when the current role or schedule ownership does not allow them.

### Schedule Horizon

- The horizon starts at the exact current time and ends 24 hours later.
- Only real enabled schedules with `next_run_at` inside that interval are plotted; no synthetic prediction is shown.
- Each schedule receives its own 21px minimum lane. The current-time line and event marker use SiftLane Blue, and the lane region scrolls vertically when necessary.

### Schedule Views And Context

- The overview uses collapsible plan-layer and task-intelligence Docks around the central timeline and a two-panel live signal deck below it.
- Dedicated plan, run, and exception screens use Ant Design tables with stable rows, keyboard selection, search, status filters, pagination, and internal horizontal scrolling.
- Overview timeline and roster selection update the right context Dock. Tags communicate status; edit and run actions remain available there when permissions allow.
- Create and edit use an Ant Design Drawer and Form with workflow, name, Cron, timezone, enabled state, and validated JSON parameters.

### Workflow Editor And Results

- React Flow remains the workflow canvas. Nodes keep compact 4px geometry, visible role distinction, and a selected/running blue lift.
- Results remain a keyboard-targetable table. Activating a result opens the independent center article-detail view with back, previous, next, original-source, and focus-restoration behavior.
- Captured article title and body may use the reading serif; navigation, metadata, controls, and provenance remain sans or mono.

## Do's and Don'ts

### Do:

- **Do** keep Task Scheduling visible as a peer primary destination.
- **Do** use Ant Design 6 for management controls and preserve its interaction states.
- **Do** derive scheduling views from real `next_run_at`, schedule, run, health, role, and ownership data.
- **Do** preserve the central situation field when either Dock collapses, and route long datasets to their dedicated views.
- **Do** keep all horizon lanes scrollable and schedule rows operable by keyboard.
- **Do** serialize create, update, enable/pause, run-now, and delete operations through the global atomic mutation lock.
- **Do** preserve workflow-editor and result-detail behavior outside scheduling mode.

### Don't:

- **Don't** present World Monitor styling, maps, or a dark surveillance aesthetic; only its information topology informed this surface.
- **Don't** fabricate future triggers, health values, run history, permissions, or scheduling policies.
- **Don't** turn the scheduling center into cards, a marketing dashboard, or a mobile claim.
- **Don't** use a Drawer for captured result detail; the Drawer belongs to schedule create/edit forms.

## Delivery Record

- **Product requirements:** `documentation/PRD-SiftLane-Task-Scheduling-Center.md`.
- **Direction contract seed:** `ec77db1e`.
- **Validated desktop captures:** `outputs/p2-scheduler.png` (1440x900) and `outputs/p2-scheduler-1280.png` (1280x800).
- **Mechanical detector:** `[]`.
- **Independent review:** PASS with no material findings.
- **Finish disposition:** **PASS**.
