/**
 * Jarvis CRM — MG&CO design tokens (dark, minimal, luxury).
 *
 * Single source of truth for the white-label look. `apply.sh` patches Twenty's theme
 * provider to (a) default the color scheme to Dark and (b) override the accent + base
 * surfaces with these values. Restyle the whole product by editing the tokens here.
 *
 * Inspiration: Notion's restraint + Spotify's depth. Near-black surfaces, a single warm
 * metallic accent (MG&CO gold), generous spacing, quiet borders.
 *
 * NOTE: token names mirror Twenty's theme shape as of v0.42. If a name moves upstream,
 * map it in apply.sh rather than scattering edits.
 */

export const jarvisBrand = {
  productName: 'Jarvis CRM',
  vendor: 'MG&CO',
  supportUrl: 'https://jarvismgco.com',
  defaultColorScheme: 'Dark' as const,
};

/** Core palette — warm metallic accent on layered near-black surfaces. */
export const jarvisPalette = {
  // Accent (MG&CO gold / amber) — primary actions, focus, active nav.
  accent: {
    primary: '#C9A24B',      // gold
    hover: '#D8B568',
    active: '#B8923F',
    subtle: 'rgba(201, 162, 75, 0.12)',
    onAccent: '#0B0B0C',     // text/icon sitting on the accent
  },

  // Dark surfaces — layered, not flat black, for depth.
  surface: {
    base: '#0B0B0C',         // app background
    raised: '#141416',       // cards, panels
    overlay: '#1B1B1E',      // modals, menus, popovers
    input: '#18181B',
    hover: 'rgba(255, 255, 255, 0.04)',
    selected: 'rgba(201, 162, 75, 0.10)',
  },

  border: {
    subtle: 'rgba(255, 255, 255, 0.06)',
    medium: 'rgba(255, 255, 255, 0.10)',
    strong: 'rgba(255, 255, 255, 0.16)',
    accent: 'rgba(201, 162, 75, 0.40)',
  },

  text: {
    primary: '#F5F5F4',      // near-white, not pure white (luxury restraint)
    secondary: '#A8A8A6',
    tertiary: '#6E6E6C',
    inverted: '#0B0B0C',
  },

  // Semantic — muted, not neon, to keep the luxury feel.
  semantic: {
    success: '#4FB477',
    warning: '#D8A24B',
    danger: '#D9534F',
    info: '#5B9BD5',
  },
} as const;

/** Typography — clean grotesque for UI, tabular numerals for CRM data. */
export const jarvisTypography = {
  fontFamily:
    "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  fontFamilyMono: "'JetBrains Mono', 'SFMono-Regular', Menlo, monospace",
  // Tight, confident headings; comfortable body.
  weight: { regular: 400, medium: 500, semibold: 600, bold: 700 },
  letterSpacingTight: '-0.01em',
} as const;

/** Shape — soft but not rounded-toy; quiet shadows. */
export const jarvisShape = {
  radius: { sm: '6px', md: '10px', lg: '14px', pill: '999px' },
  shadow: {
    raised: '0 1px 2px rgba(0,0,0,0.4)',
    overlay: '0 8px 32px rgba(0,0,0,0.55)',
  },
} as const;

export const jarvisTheme = {
  brand: jarvisBrand,
  palette: jarvisPalette,
  typography: jarvisTypography,
  shape: jarvisShape,
};

export default jarvisTheme;
