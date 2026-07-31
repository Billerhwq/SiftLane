# Control Room

This surface brief documents the shipped Siftlane Cloud Blue Console control room. It overrides the generated dark baseline in `../siftlane/MASTER.md`; the root `DESIGN.md` and this file are authoritative for this surface.

## Mode

**Operate.** Users repeatedly select a flow, inspect or edit its declared DAG, run it, follow live activity, and inspect durable results and events.

## Direction Contract

- **THESIS:** The live execution path is the workspace. The surface refuses a dashboard made from detached metric cards.
- **OWN-WORLD:** Cloud-blue actions, cool-white rails, a pale-blue graph field, compact square controls, and independent semantic status colors establish Siftlane's own visual world.
- **STORY:** Operators select a flow, edit its inspectable DAG, run it, follow two live lines, then inspect the durable event and item record.
- **FIRST VIEWPORT:** A narrow flow rail, full-scale workflow canvas, and contextual inspector share one continuous control room beneath engine health. On mobile, explicit edge controls replace the rails while the graph and live activity remain visible.
- **FORM:** User-locked Cloud Blue Console from approved prototype D, seed key `PROTOTYPE-D-20260731`.

## Shipped Composition

### Desktop

- A 60px top bar and 62px engine/status strip span the full shell.
- The main work area uses a 232px flow rail, flexible workflow canvas, and 320px node inspector.
- The center view uses a 46px tab/action bar, flexible graph or data view, and 108px event dock.
- The dotted Graph Mist canvas is the dominant region. Nodes remain fixed at 188x104px and carry visible handles and edge state.
- Results and run history replace only the center view. Flow selection, engine status, actions, inspector, and live dock stay in place.

### Mobile

- At 900px and below, the flow rail becomes a left drawer and the inspector becomes a right drawer; breadcrumbs, desktop-only actions, counters, and the minimap collapse.
- At 560px and below, the shell uses 54px top and status rows, a 44px workspace bar, and a 94px live dock.
- Familiar command icons replace labels where width is constrained. Every icon control keeps an accessible name or tooltip.
- The graph remains full scale and pannable. The viewport may show only the currently relevant middle nodes; it does not shrink the workflow into unreadable miniatures.
- Live activity retains two message lines while timestamps and event types defer to the expanded ledger.

## View States

### Edit

The graph title anchors the upper-left of the canvas. The flow runs horizontally through compact rectangular nodes; selected or running nodes use a 2px Console Blue boundary, completed paths and written states use Execution Green, and failed nodes use Failure Red. The right inspector exposes schema-backed fields, a written policy note, recent run summary, and the destructive delete action.

### Results

The Results tab swaps the canvas for a scrollable table with a sticky header and 760px content minimum. Long URLs, descriptions, and identifiers truncate inside stable columns. The inspector and event dock remain visible so output stays connected to its configuration and run evidence.

### Live Activity And Ledger

The persistent event dock exposes no more than the two latest lines. Its complete ordered ledger opens upward from the dock, up to 340px high, without changing shell geometry or moving the user's graph position. Desktop rows preserve sequence, message, event type, and time; mobile drops the type column first.

## Surface Tokens

Use the root `DESIGN.md` frontmatter as the normative token source. The shipped values that most strongly shape this surface are:

```css
--brand: #0052d9;
--brand-hover: #003eb3;
--brand-soft: #e8f2ff;
--canvas: #f5f9fd;
--surface: #ffffff;
--text: #1b2b42;
--muted: #60748b;
--line: #dce4ec;
--line-strong: #bac7d5;
--success: #007a52;
--warning: #c45f18;
--danger: #c93535;
```

## Interaction And Accessibility

- Primary, secondary, icon, tab, node, row, drawer, and disclosure controls all have visible hover or selected states.
- Keyboard focus uses a 2px Console Blue outline with a 2px offset; schema fields use the same blue border plus a restrained halo.
- Disabled controls retain geometry and reduce opacity to 48%.
- Semantic states combine color with labels, event text, or icons.
- The two-line activity region is a polite live region; the ordered ledger remains available on demand.
- Drawer motion is 220ms with `cubic-bezier(.2,.8,.2,1)` and state transitions are 160ms ease. `prefers-reduced-motion` reduces animation and transition duration to 0.01ms.
- The shell starts at a 320px minimum width and avoids document-level horizontal or vertical scrolling.

## Product Boundary

- The visible node vocabulary is `start`, `http_request`, `html_extract`, `json_extract`, `condition`, `loop`, `pagination`, `transform`, and `emit`.
- The UI may show the shipped connector surface and real engine evidence, but it must not present browser automation, authenticated platform adapters, or arbitrary Python/JavaScript execution as available.
- Do not invent production metrics, certified connectors, customer proof, or platform capability states.
- Do not import or mimic SubtleSight components, tokens, navigation, wordmark, dark shell, AI-assistant styling, or document-editor patterns.

## Guardrails

- Keep the graph as the largest and clearest working region.
- Keep live activity to two persistent lines and disclose full history upward from its dock.
- Keep controls compact, rectangular, and aligned to fixed dimensions.
- Preserve semantic green, amber, and red; do not make every state blue.
- Do not add generic dashboard cards, oversized metrics, decorative gradients, glass effects, nested cards, or marketing composition.
- Keep node, event, result, and inspector content readable at 1440x900 and 390x844 without document-level scrolling.

## Finish Review

**Disposition: PASS**

- **THESIS: RESOLVED.** The workflow graph, not a metric-card dashboard, owns the dominant area in edit state; results remain connected to the same operational shell.
- **OWN-WORLD: RESOLVED.** The Siftlane lane mark, Console Blue, Graph Mist, cool-white rails, square controls, and semantic execution states form a coherent independent identity.
- **STORY: RESOLVED.** Flow selection, declared graph editing, run action, two-line live activity, results, and the durable ordered event ledger are all present in one observable sequence.
- **FIRST VIEWPORT: RESOLVED.** Desktop shows flow context, engine health, full-scale graph, inspector, and live evidence together. Mobile preserves brand, engine state, graph, run controls, and live activity while moving side context behind explicit controls.
- **FORM: RESOLVED.** The shipped implementation matches the user-locked Cloud Blue Console direction from prototype D without drifting toward the generated dark baseline.

Evidence: `outputs/p1-desktop.png`, `outputs/p1-desktop-results.png`, `outputs/p1-mobile.png`, `outputs/p2-branch-retry.png`, and `outputs/p2-scheduler.png`.
