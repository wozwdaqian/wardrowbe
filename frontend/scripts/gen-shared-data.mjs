#!/usr/bin/env node
// Writes lib/generated/*.ts from the JSON files in backend/app/data, which are the only places
// garment vocabulary (types, roles, materials, formality, occasions, colours and colour aliases),
// locale codes, the rating, temperature threshold, repeat-avoidance and style score scales, and the
// preference defaults are edited by hand. Run with --check to fail when any committed output is stale. It reads ../backend, which
// is outside the frontend Docker build context, so it must never run from build or prebuild.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DATA_DIR = resolve(ROOT, '..', 'backend', 'app', 'data');
const OUTPUT_DIR = resolve(ROOT, 'lib', 'generated');

const quote = (value) => `'${value}'`;
const key = (value) => (/^[A-Za-z_][A-Za-z0-9_]*$/.test(value) ? value : quote(value));
const list = (values) => `[${values.map(quote).join(', ')}] as const`;
const header = (source) => [
  `// Generated from backend/app/data/${source} by scripts/gen-shared-data.mjs.`,
  '// Do not edit by hand; run `npm run vocab:gen`.',
];

function renderVocabulary({ roles: roleOrder, types, materials, formality, occasions, colors, color_aliases: colorAliases }) {
  const roles = types.map(({ value, role }) => `  ${key(value)}: ${quote(role)},`).join('\n');
  const swatches = colors.map(({ value, hex }) => `  { value: ${quote(value)}, hex: ${quote(hex)} },`).join('\n');
  const aliases = Object.entries(colorAliases)
    .map(([alias, color]) => `  ${key(alias)}: ${quote(color)},`)
    .join('\n');
  return [
    `export const CLOTHING_TYPE_VALUES = ${list(types.map((t) => t.value))};`,
    `export const MATERIAL_VALUES = ${list(materials)};`,
    `export const FORMALITY_VALUES = ${list(formality)};`,
    `export const OCCASION_VALUES = ${list(occasions.map((o) => o.value))};`,
    `export const ROLE_VALUES = ${list(roleOrder)};`,
    '',
    'export const ITEM_ROLE: Record<string, string> = {',
    roles,
    '};',
    '',
    'export const CLOTHING_COLORS = [',
    swatches,
    '] as const;',
    '',
    'export const COLOR_ALIASES: Record<string, string> = {',
    aliases,
    '};',
  ];
}

function renderLocales({ default: defaultLocale, supported }) {
  if (!supported.includes(defaultLocale)) {
    throw new Error(`locales.json: default '${defaultLocale}' is not in supported`);
  }
  return [
    `export const SUPPORTED_LOCALES = ${list(supported)};`,
    `export const DEFAULT_LOCALE = ${quote(defaultLocale)} as const;`,
  ];
}

function renderScales({
  rating,
  temperature_thresholds_celsius: thresholds,
  avoid_repeat_days: avoidRepeat,
  style_score: styleScore,
}) {
  const bound = ({ min, max, default: fallback }) =>
    `{ min: ${min}, max: ${max}, default: ${fallback} }`;
  return [
    `export const RATING_MIN = ${rating.min};`,
    `export const RATING_MAX = ${rating.max};`,
    '',
    'export const TEMPERATURE_THRESHOLDS_CELSIUS = {',
    `  cold: ${bound(thresholds.cold)},`,
    `  hot: ${bound(thresholds.hot)},`,
    '} as const;',
    '',
    `export const AVOID_REPEAT_DAYS = ${bound(avoidRepeat)} as const;`,
    `export const STYLE_SCORE = ${bound(styleScore)} as const;`,
  ];
}

function renderPreferenceDefaults(defaults) {
  const literal = (value) => (typeof value === 'string' ? quote(value) : String(value));
  const entries = Object.entries(defaults).map(([name, value]) => `  ${key(name)}: ${literal(value)},`);
  return ['export const PREFERENCE_DEFAULTS = {', ...entries, '} as const;'];
}

// Only ids, base styles and names; descriptions and looks are served by the style quiz API.
function renderJapaneseStyles({ styles }) {
  const bases = styles.map(({ id, base_style: base }) => `  ${key(id)}: ${quote(base)},`);
  const names = styles.map(
    ({ id, name }) => `  ${key(id)}: { zh: ${quote(name.zh)}, en: ${quote(name.en)}, ja: ${quote(name.ja)} },`,
  );
  return [
    `export const JAPANESE_STYLE_IDS = ${list(styles.map((s) => s.id))};`,
    'export type JapaneseStyleId = (typeof JAPANESE_STYLE_IDS)[number];',
    '',
    'export const JAPANESE_STYLE_BASE: Record<JapaneseStyleId, string> = {',
    ...bases,
    '};',
    '',
    'export const JAPANESE_STYLE_NAMES: Record<JapaneseStyleId, { zh: string; en: string; ja: string }> = {',
    ...names,
    '};',
  ];
}

const TARGETS = [
  { source: 'garment_vocabulary.json', output: 'garment-vocabulary.ts', render: renderVocabulary },
  { source: 'locales.json', output: 'locales.ts', render: renderLocales },
  { source: 'scales.json', output: 'scales.ts', render: renderScales },
  { source: 'preference_defaults.json', output: 'preference-defaults.ts', render: renderPreferenceDefaults },
  { source: 'japanese_styles.json', output: 'japanese-styles.ts', render: renderJapaneseStyles },
  // JSON cannot carry the generated header, so the body styling catalog is mirrored verbatim.
  { source: 'body_styling_catalog.json', output: 'body-styling-catalog.json', raw: true },
];

const check = process.argv.includes('--check');
let stale = false;

for (const { source, output, render, raw } of TARGETS) {
  const data = JSON.parse(readFileSync(resolve(DATA_DIR, source), 'utf8'));
  const expected = raw
    ? `${JSON.stringify(data, null, 2)}\n`
    : [...header(source), ...render(data), ''].join('\n');
  const path = resolve(OUTPUT_DIR, output);

  if (check) {
    const current = existsSync(path) ? readFileSync(path, 'utf8') : null;
    if (current !== expected) {
      console.error(`lib/generated/${output} is out of date with backend/app/data/${source}; run \`npm run vocab:gen\`.`);
      stale = true;
    }
  } else {
    mkdirSync(OUTPUT_DIR, { recursive: true });
    writeFileSync(path, expected);
    console.log(`Wrote ${path}`);
  }
}

if (check) {
  if (stale) process.exit(1);
  console.log('vocab-check: OK');
}
