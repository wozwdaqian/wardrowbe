// Generated from backend/app/data/japanese_styles.json by scripts/gen-shared-data.mjs.
// Do not edit by hand; run `npm run vocab:gen`.
export const JAPANESE_STYLE_IDS = ['cityboy', 'amekaji', 'workwear', 'yamakei', 'vintage', 'natural', 'kireime', 'ivy', 'normcore', 'mode', 'ura_street'] as const;
export type JapaneseStyleId = (typeof JAPANESE_STYLE_IDS)[number];

export const JAPANESE_STYLE_BASE: Record<JapaneseStyleId, string> = {
  cityboy: 'street',
  amekaji: 'street',
  workwear: 'street',
  yamakei: 'sporty',
  vintage: 'street',
  natural: 'minimal',
  kireime: 'smart_casual',
  ivy: 'classic',
  normcore: 'minimal',
  mode: 'minimal',
  ura_street: 'street',
};

export const JAPANESE_STYLE_NAMES: Record<JapaneseStyleId, { zh: string; en: string; ja: string }> = {
  cityboy: { zh: 'Cityboy 城市男孩', en: 'City Boy', ja: 'シティボーイ' },
  amekaji: { zh: '阿美咔叽', en: 'Amekaji', ja: 'アメカジ' },
  workwear: { zh: '日式工装 · 军装', en: 'Japanese workwear & military', ja: 'ワーク・ミリタリー' },
  yamakei: { zh: '山系 · 户外', en: 'Yamakei outdoor', ja: '山系・アウトドア' },
  vintage: { zh: '古着复古', en: 'Vintage (furugi)', ja: '古着・ヴィンテージ' },
  natural: { zh: '文艺森系 · 无印风', en: 'Natural (Mori, Muji-like)', ja: 'ナチュラル系' },
  kireime: { zh: 'きれいめ 清爽干净', en: 'Kireime (clean & neat)', ja: 'きれいめ系' },
  ivy: { zh: '日式常春藤 · 学院', en: 'Japanese Ivy & trad', ja: 'アイビー・トラッド' },
  normcore: { zh: '极简基础 · Normcore', en: 'Normcore basics', ja: 'ノームコア' },
  mode: { zh: '暗黑 Mode', en: 'Mode (dark avant-garde)', ja: 'モード系' },
  ura_street: { zh: '日式街头 · 里原宿', en: 'Japanese street (Ura-Harajuku)', ja: 'ストリート系' },
};
