# Lane Studio Control Room

This surface brief documents the shipped SiftLane Lane Studio workspace. It replaces the former Cloud Blue Console direction. The root `DESIGN.md` is the normative token source and this file owns composition, view-state, and interaction decisions for the control room.

## Mode

**Operate**, with a focused **Read** state for captured article detail. Users build and run declared crawler workflows, inspect live evidence, scan normalized results, and then read the complete captured item without leaving the studio.

## Direction Contract

- **THESIS:** The crawler lane and its evidence are one continuous workbench. The product refuses detached dashboard cards and transient item-detail overlays.
- **OWN-WORLD:** A full-viewport white studio, quiet neutral rails, Lane Blue actions, colored node-role tiles, and editorial result detail establish SiftLane's visual identity.
- **STORY:** Select a flow, inspect or edit the declared DAG, run it, follow live activity, scan results, then switch the center surface to complete article detail and return to the originating row.
- **FIRST VIEWPORT:** Desktop shows the utility rail, flow library, central graph or evidence surface, inspector, engine state, and live event dock together. Mobile retains only the context needed for the current task and moves secondary rails behind explicit controls.
- **FORM:** User-approved Lane Studio interpretation of the supplied reference, seed key `a31d7c33`.

## Shipped Composition

### Desktop

- The application fills the browser viewport without an outer margin and uses a 62px top bar plus a 44px engine/status strip.
- Four columns organize the working area: 64px utility rail, 248px flow rail, flexible center with a 580px minimum, and 316px inspector.
- The center stacks a 52px workspace bar, a flexible graph/results/detail view, and a 96px live event dock.
- The utility rail provides stable icon access to primary product areas. The flow rail carries search, flows, recent runs, and local-network status.
- Workflow nodes are fixed at 196x110px. Their bodies remain neutral while node-role icon tiles use restrained green, blue, coral, sun, mint, and violet families.

### Responsive

- At 1280px, the columns compact to 60px, 220px, flexible center, and 288px inspector.
- At 960px and below, the flow rail and inspector become explicit edge panels. The 60px utility rail remains visible until the mobile breakpoint.
- At 680px and below, the utility rail disappears. The app remains a one-column full-viewport shell, and top-level actions collapse to symbols.
- In mobile detail mode, top and status rows compress, the workspace tab row disappears, the article receives the flexible center, and every detail command is at least 44px.

## View States

### Workflow

The graph owns the central workspace. A flow runs horizontally through role-colored nodes with visible handles and readable state labels. Selected and running nodes use a 2px Lane Blue boundary and active lift. Completed and failed states use independent green and coral treatments.

### Results

The Results tab replaces the graph with a scrollable 7px framed table. The sticky header remains 40px high and result rows remain 52px high regardless of content. Long values truncate in their cells. Pointer activation, Enter, or Space opens the selected item.

### Item Detail

Item detail is an independent center panel, never a drawer or dialog. Its sticky toolbar provides return, previous, next, and original-source actions. The document column uses the reading serif for title and body; the adjacent facts column exposes source, author, original publication time, capture time, media type, content length, external ID, and complete metadata.

Opening detail moves keyboard focus to its title. Escape returns to Results, left and right arrows navigate adjacent items, and returning restores focus to the originating result row. On small screens the facts column follows the article body so reading width remains stable.

### Live Activity And Ledger

The persistent event dock retains the two latest evidence lines and current connection state. The complete ordered ledger opens upward from that dock without moving the user's canvas, result list, or article position.

## Data Collection Journey

The shipped crawl path is observable end to end:

1. A listing request retrieves a news index or hotspot page.
2. HTML extraction produces article titles and relative or absolute links.
3. Relative links are resolved against the listing URL.
4. A loop requests each article detail page.
5. Detail extraction merges matching body elements and extracts author and publication time.
6. Emit writes normalized items with article URL, full content, provenance, and nested metadata.
7. Results expose the normalized rows; item detail exposes the complete captured record.

JSON and JSONP sources may enter through the equivalent JSON extraction path. Metadata templates may use nested structures, and emitted values remain inspectable in the detail facts panel.

## Surface Tokens

Use the root `DESIGN.md` frontmatter as the normative token source. The values that most strongly shape this surface are:

```css
--brand: #3568c8;
--brand-hover: #28539f;
--brand-soft: #edf3ff;
--canvas: #f7f9fc;
--surface: #ffffff;
--surface-subtle: #f6f8fa;
--text: #202124;
--muted: #667085;
--line: #e2e6eb;
--line-strong: #c9d0d9;
--success: #2f7a44;
--warning: #ad6516;
--danger: #be4c45;
--accent-sun: #f0cc68;
--accent-coral: #eaa39d;
--accent-mint: #78bf95;
```

## Motion And Accessibility

- Canvas, result, detail, and empty-state views enter with a bounded 320ms surface transition using `cubic-bezier(.16, 1, .3, 1)`.
- Engine health uses a slow 2.6s breathing cue. Reduced-motion preference removes all view and health animation.
- Primary, secondary, icon, tab, node, row, edge-panel, and disclosure controls expose visible hover, selected, and keyboard-focus states.
- All icon commands use Lucide icons and carry an accessible name or native tooltip.
- Semantic states combine color with text, icons, or both.
- Result rows are keyboard targets, detail headings receive programmatic focus, and the list-to-detail-to-list sequence preserves keyboard continuity.
- Mobile detail commands meet the 44px minimum touch target.

## Product Boundary

- The visible node vocabulary is `start`, `http_request`, `html_extract`, `json_extract`, `condition`, `loop`, `pagination`, `transform`, and `emit`.
- The UI presents only local engine evidence and implemented connectors. It does not imply browser automation, authenticated platform adapters, or arbitrary Python/JavaScript execution.
- Detail values come from the normalized emitted item; absent author or source values use an honest fallback.
- No production metrics, certified connector claims, customer proof, cloud deployment state, or Docker requirement belongs in this local-only surface.

## Guardrails

- Keep the active workflow or evidence view as the largest working region.
- Keep item detail as a center-view replacement, never a transient overlay.
- Keep controls, nodes, table rows, and dock regions dimensionally stable.
- Preserve role accents and semantic green, amber, and coral instead of making every state blue.
- Avoid bento cards, nested cards, oversized metrics, marketing composition, decorative gradients, glass effects, and text pills.
- Keep the interface readable at 1440x900 and 390x844 without document-level scrolling or overlapping controls.

## Finish Review

**Disposition: PASS**

- **THESIS: RESOLVED.** Workflow, result evidence, and complete item detail occupy the same center workspace and preserve surrounding context.
- **OWN-WORLD: RESOLVED.** The full-viewport studio, functional rail, colored node roles, restrained palette, and editorial detail state form a coherent SiftLane identity.
- **STORY: RESOLVED.** Listing extraction, link resolution, detail requests, full-content extraction, normalized output, result scanning, and detail reading form one visible workflow.
- **FIRST VIEWPORT: RESOLVED.** Desktop preserves the full operating context. Mobile prioritizes reading and commands while collapsing secondary rails.
- **FORM: RESOLVED.** The implementation follows the approved Lane Studio direction and the supplied reference without reverting to the old console visual world.
- **KEYBOARD: RESOLVED.** Detail focus, Escape return, arrow navigation, and row focus restoration complete the result-detail interaction.
- **MOBILE: RESOLVED.** Detail mode gives the reading surface most of the viewport and expands primary commands to 44px.
- **CONTRAST: RESOLVED.** Secondary labels and evidence text use the final Measured Gray token against white and quiet surfaces.

Evidence: `outputs/item-detail-desktop.png`, `outputs/item-detail-mobile.png`, plus the existing P1-P5 workflow and operations captures in `outputs/`.
