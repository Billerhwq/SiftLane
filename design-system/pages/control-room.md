# SiftLane Task Scheduling Control Room

This surface brief documents the shipped desktop-Web Task Scheduling center. The root `DESIGN.md` is the normative token source, `documentation/PRD-SiftLane-Task-Scheduling-Center.md` defines the shipped product scope, and this file owns the scheduling page's composition, state, and interaction contract.

## Mode And Scope

**Operate.** The page lets an operator scan schedule health, locate the next trigger, manage a plan, and enter the corresponding run record without leaving the SiftLane workspace.

This redesign is accepted at 1440x900 and 1280x800 only. It does not state mobile acceptance or mobile capabilities.

## Direction Contract

- **THESIS:** Scheduling is a first-class operating center, not a secondary Drawer attached to the workflow editor.
- **OWN-WORLD:** A bright, continuous SiftLane shell, precise blue action cues, low-radius Ant Design controls, and real operational data define the page.
- **STORY:** Enter Task Scheduling, scan system state, inspect the exact 24-hour horizon and live signals, select a plan for context, then enter a dedicated management, run, or exception view when the dataset needs sustained work.
- **FIRST VIEWPORT:** The persistent primary navigation, status strip, schedule header, six-part summary, collapsible left roster, dominant central horizon, bottom signal deck, and collapsible right intelligence Dock remain visible together.
- **FORM:** Direction contract seed `ec77db1e`.

World Monitor owns the overview topology: a dominant central situation field, peripheral Docks, a bottom live-signal deck, and view switching above the field. It did not supply the visual style, palette, map treatment, or interaction components. Ant Design 6 owns management controls, menus, tables, search and segmented filters, forms, Drawer, confirmations, and tags.

## Shipped Composition

### Application Shell

- The page keeps Task Scheduling in the first-class left navigation beside Workflow Editor, Run History, and Collection Results.
- The shell uses a 56px top bar and 44px status strip. The navigation is 188px wide at 1440px and compacts to 64px at 1280px.
- Scheduling replaces the center workspace and hides workflow-only rails, inspector, workspace tabs, and event dock. It does not alter their behavior in the other primary modules.

### Scheduling Header And Summary

- A stable 60px page header contains the title, refresh, and permission-aware create action.
- A 44px strip reports total plans, enabled, paused, error, running, and queued counts from current schedule, run, and health data.

### View Routing

- **Situation:** the default information-screen overview for scanning the next 24 hours and current live signals.
- **Plan management:** a dedicated full-width Ant Design table for search, filtering, selection, and plan actions.
- **Run records:** a dedicated full-width table with run-specific search and status filters.
- **Exception center:** a dedicated screen switching between problem schedules and failed runs.

### Collapsible Situation Topology

- **Left roster:** Search by schedule or workflow name, filter by all/enabled/paused/error, and scan the scrollable upcoming list sorted by real `next_run_at`.
- **Center field:** The exact current-time-to-plus-24-hours railway band dominates the workspace, with risk and execution-signal panels docked beneath it.
- **Right context:** The selected schedule's status, workflow, next/last run, timezone, Cron, and last error sit above a scrollable live run ledger.

At 1440px the expanded field is 220px / flexible center / 290px. Either side independently collapses to a 44px summary rail, and the preference persists in local storage. At 1280px the right Dock starts collapsed on first use, allowing the central field to own almost the entire available width; users can reopen it at any time. Collapsed controls expose `aria-expanded` and `aria-controls`.

## Horizon Contract

- The horizon starts from `Date.now()` and ends exactly 24 hours later.
- It plots only enabled schedules whose real `next_run_at` lies inside that interval.
- Each trigger receives its own lane and precise time position; no synthetic recurrence or forecast is generated.
- All qualifying lanes remain available inside the flexible, vertically scrollable lane region.
- The axis, current-time rule, event marker, schedule name, workflow name, and exact trigger time provide the complete reading context.

## Schedule Management

- Search and segmented filtering update the overview roster and horizon; the plan-management view reuses the same query state for its full dataset.
- Table rows are pointer and keyboard targets. Enter or Space selects a row and updates the right context panel.
- CRUD is shipped through the existing schedule API. Create and edit use an Ant Design Drawer and Form; JSON parameters are parsed and validated before submission.
- Enable/pause, edit, run-now, and delete actions honor the current user's role, schedule ownership/creator relationship, and visibility rules.
- Run now triggers the schedule, inserts the returned run into current query data, navigates to Run History, and selects that run.
- A single global atomic mutation lock serializes create, update, enable/pause, run-now, and delete operations; other schedule actions remain disabled until the active mutation finishes.
- Success and failure feedback is explicit. Delete requires confirmation.

## Component And Token Contract

Ant Design 6 is the authority for management behavior and control state. Lucide provides interface icons with accessible names or tooltips.

```css
--primary: #002fa7;
--primary-hover: #00257f;
--primary-soft: #eaf0ff;
--canvas: #f4f6f9;
--text: #172033;
--muted: #657084;
--line: #d9dde5;
--success: #16865c;
--warning: #b96d00;
--danger: #c53b3f;
```

- Radius range: 4-6px.
- Ant Design base font: 12px.
- Scheduling operational minimum: 10px.
- Standard control height: 34px.
- Dedicated data views use compact, stable Ant Design table rows and internal horizontal scrolling where necessary.
- Static scheduling regions are flat and separated by hairlines; Drawer, confirmation, and transient feedback may elevate.

## Workflow And Results Continuity

The redesign adds scheduling as a peer module without replacing the shipped workflow editor or results experience:

- React Flow continues to own workflow composition and node interaction.
- Run History remains the destination for the run returned by run now.
- Results remain keyboard-selectable, and captured item detail remains an independent center view rather than a Drawer or dialog.
- Article detail retains back, previous, next, original-source, focus entry, and originating-row focus restoration.

## Accessibility And Boundaries

- Primary navigation, view tabs, Dock controls, timeline markers, filters, table rows, row actions, schedule forms, and live ledger entries expose keyboard and focus states.
- Status combines text or iconography with color.
- Permission-denied actions are visibly disabled rather than offered optimistically.
- Empty, loading, no-match, API error, and last-error states use honest data and explicit feedback.
- The page does not claim unimplemented recurrence forecasts, advanced scheduling policies, batch management, server pagination, saved filters, or mobile behavior.

## Finish Review

**Disposition: PASS**

- **THESIS: RESOLVED.** Task Scheduling is a first-class primary module with its own full operating field.
- **OWN-WORLD: RESOLVED.** SiftLane's bright, compact operations language and Ant Design 6 management grammar are consistent across the page.
- **STORY: RESOLVED.** Search/filter, selection, CRUD, enable/pause, run now, and run-history navigation form a complete shipped path.
- **FIRST VIEWPORT: RESOLVED.** The exact 24-hour horizon is dominant; peripheral Docks and the bottom live-signal deck retain context without competing with it.
- **COLLAPSE: RESOLVED.** Both Docks independently collapse to 44px summaries, restore without data loss, persist locally, and default intelligently at 1280px.
- **LARGE DATA: RESOLVED.** Plans, runs, and exceptions live in dedicated full-width views; overview feeds are capped and link to the complete datasets.
- **DATA: RESOLVED.** The horizon uses real `next_run_at`; actions use current role and ownership data; no forecast is fabricated.
- **KEYBOARD: RESOLVED.** Schedule rows are selectable with Enter and Space, and management controls expose native focus behavior.
- **CONCURRENCY: RESOLVED.** The global atomic mutation lock prevents overlapping schedule mutations.

Evidence: `outputs/p2-scheduler.png` (1440x900 overview), `outputs/p2-scheduler-1280.png` (1280x800 collapsed overview), `outputs/p2-scheduler-plans.png`, and `outputs/p2-scheduler-runs.png`. Mechanical detector result: `[]`. Independent reviewer: final PASS with no material findings.
