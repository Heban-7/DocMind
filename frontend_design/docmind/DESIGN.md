---
name: DocMind
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#464555'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#777587'
  outline-variant: '#c7c4d8'
  surface-tint: '#4d44e3'
  primary: '#3525cd'
  on-primary: '#ffffff'
  primary-container: '#4f46e5'
  on-primary-container: '#dad7ff'
  inverse-primary: '#c3c0ff'
  secondary: '#565e74'
  on-secondary: '#ffffff'
  secondary-container: '#dae2fd'
  on-secondary-container: '#5c647a'
  tertiary: '#7e3000'
  on-tertiary: '#ffffff'
  tertiary-container: '#a44100'
  on-tertiary-container: '#ffd2be'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e2dfff'
  primary-fixed-dim: '#c3c0ff'
  on-primary-fixed: '#0f0069'
  on-primary-fixed-variant: '#3323cc'
  secondary-fixed: '#dae2fd'
  secondary-fixed-dim: '#bec6e0'
  on-secondary-fixed: '#131b2e'
  on-secondary-fixed-variant: '#3f465c'
  tertiary-fixed: '#ffdbcc'
  tertiary-fixed-dim: '#ffb695'
  on-tertiary-fixed: '#351000'
  on-tertiary-fixed-variant: '#7b2f00'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  display:
    fontFamily: Geist
    fontSize: 48px
    fontWeight: '600'
    lineHeight: '1.1'
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Geist
    fontSize: 32px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.2'
  headline-md:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '500'
    lineHeight: '1.3'
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.6'
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
  label-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '500'
    lineHeight: '1.2'
    letterSpacing: 0.02em
  code:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '1.6'
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 48px
  container-max: 1440px
  gutter: 24px
  margin-mobile: 16px
---

## Brand & Style
The design system is engineered for high-stakes enterprise document intelligence. The brand personality is **authoritative, precise, and unobtrusive**, prioritizing the user’s content over decorative UI. 

Drawing from **Minimalism** and **Glassmorphism**, the system utilizes a "Focus-First" philosophy. By stripping away unnecessary gradients and ornaments, the UI recedes into the background, allowing complex data and long-form text to take center stage. The emotional response is one of calm productivity and high-trust reliability. Visual interest is generated through perfect alignment, intentional whitespace, and a single, sharp accent that cuts through a sophisticated monochromatic environment.

## Colors
The palette is rooted in a **Sophisticated Monochrome** foundation. It uses high-contrast values to ensure legibility and structural clarity in both light and dark modes.

- **Primary:** An electric indigo used sparingly for primary actions, active states, and critical paths.
- **Monochrome Base:** A range of slates and charcoals. In Light Mode, use `Slate-50` for backgrounds and `Slate-900` for text. In Dark Mode, use `Slate-950` for backgrounds and `Slate-50` for text.
- **Functional Accents:** Success, warning, and error states use solid, high-saturation colors without gradients to maintain the professional, "auditable" aesthetic.
- **Glassmorphism:** Navigation headers and sidebars utilize a 70% opacity fill of the background color with a 20px blur to create a sense of depth and layering without breaking the minimalist color constraints.

## Typography
This design system employs a dual-font strategy to balance technical precision with reading comfort.

- **Geist** is used for headings, labels, and UI elements. Its geometric rigour reflects the "intelligent" and "technical" nature of the product.
- **Inter** is used for all body copy and document-heavy views. It provides exceptional legibility for the long-form text analysis typical of enterprise SaaS.

**Hierarchy Rules:**
- Use **Display** styles only for landing pages or empty states.
- Maintain a high contrast between headings (SemiBold/Medium) and body text (Regular).
- Paragraph spacing should be generous—equivalent to 1em—to prevent "text fatigue" during audit tasks.

## Layout & Spacing
The layout follows a **Fluid Grid** model with a strict 4px baseline rhythm. 

- **Desktop (1280px+):** 12-column grid. Sidebars are fixed at 280px. Main content area uses a maximum readable width of 800px for document views, centered within the remaining space.
- **Tablet (768px - 1279px):** 8-column grid. Sidebars collapse into icons or hidden drawers.
- **Mobile (<767px):** 4-column grid with 16px side margins.

**Whitespace Philosophy:**
Use "Macro-whitespace" (48px+) to separate major sections like Document Headers from Content. Use "Micro-whitespace" (8px-16px) for internal component grouping. The goal is to create a "breathable" interface that reduces cognitive load.

## Elevation & Depth
Elevation is communicated through **Tonal Layering** and **Subtle Shadows**, avoiding heavy physical metaphors.

- **Level 0 (Base):** The primary background color.
- **Level 1 (Card/Surface):** A subtle 1px border (`Slate-200` in light / `Slate-800` in dark). No shadow.
- **Level 2 (Dropdowns/Popovers):** A soft, diffused shadow: `0 10px 15px -3px rgba(0,0,0,0.1)`. 
- **Glassmorphism Effect:** Applied to global navigation (Top Bar/Sidebar). Use a backdrop filter blur (20px) and a semi-transparent background (70% opacity). This maintains context of the scroll position while providing a high-fidelity, "modern" feel.

## Shapes
The shape language is consistent with **Shadcn UI** patterns: refined and professional.

- **Standard Radius:** 0.5rem (8px) for buttons, inputs, and small widgets.
- **Large Radius (rounded-lg):** 1rem (16px) for cards and main content containers.
- **Interactive Elements:** Use 0.5rem for most triggers. Pill-shapes are reserved exclusively for status "badges" or "tags" to distinguish them from actionable buttons.

## Components

### Buttons
- **Primary:** Solid `Slate-900` (Light) or `White` (Dark) with high-contrast text. No gradients.
- **Secondary:** Ghost style with a 1px border. 
- **Accent:** Use the Primary Indigo only for the main "Call to Action" on a screen.

### Input Fields
- **Default:** Transparent background with a 1px `Slate-200` border.
- **Focus:** 1px `Indigo-500` border with a subtle 2px indigo outer glow (ring).
- **Typography:** Labels should be `label-md` in `Slate-500`.

### Cards
- Cards use the `Level 1` elevation (1px border, no shadow). 
- Internal padding should be `24px` (lg spacing) to maintain the minimalist focus.

### Lists & Tables
- Enterprise data must be dense but readable. Use 1px horizontal dividers only. 
- Alternating row stripes are discouraged; use hover states (subtle gray tint) to highlight current focus.

### Status Indicators
- Use small, solid circles next to text. Green for "Audited", Yellow for "Pending", Red for "Flagged". These are the only areas where saturated color (other than indigo) is permitted.