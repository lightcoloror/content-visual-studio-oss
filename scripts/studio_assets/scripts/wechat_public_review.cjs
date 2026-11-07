// Local adaptation of the pinned Ryan formatter. No source checkout edits or I/O beyond these outputs.
const fs = require('node:fs');
const path = require('node:path');
const [source, input, out] = process.argv.slice(2);
const {renderMarkdown} = require(path.join(source, 'scripts/presets/base.js'));
const original = require(path.join(source, 'scripts/presets/elegant-minimal/index.js'));
const {simulateDark} = require(path.join(source, 'scripts/utils/dark-preview.js'));
const data = JSON.parse(fs.readFileSync(input, 'utf8'));
const escape = text => String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const font = 'font-family:system-ui,-apple-system,"Microsoft YaHei",sans-serif;letter-spacing:0;';
const styles = {...original.STYLES,
  outer: original.STYLES.outer + 'letter-spacing:0;text-align:left;',
  p: `${font}font-size:17px;line-height:1.9;color:rgb(51,51,51);margin:0;padding:0;overflow-wrap:anywhere;`,
  h1: `${font}font-size:26px;line-height:1.5;font-weight:700;color:rgb(30,30,30);margin:24px 0;overflow-wrap:anywhere;`,
  h2: `${font}font-size:20px;line-height:1.6;font-weight:700;color:rgb(30,30,30);margin:30px 0 12px;overflow-wrap:anywhere;`,
  h3: `${font}font-size:18px;line-height:1.6;font-weight:700;margin:24px 0 10px;`,
};
// Upstream interpolates styles into double-quoted attributes without escaping.
for (const key of Object.keys(styles)) styles[key] = styles[key].replace(/"/g, "'");
let firstTitle = true;
const preset = {...original, STYLES: styles, decorations: {...original.decorations,
  parseInline(text) {
    if (!Object.hasOwn(data.inlines, text)) throw new Error('unsupported_inline_layout:' + text.slice(0, 40));
    return data.inlines[text];
  },
  makeH1(text, counter, parseInline, S) {
    if (firstTitle) { firstTitle = false; return ''; }
    return `<h2 style="${escape(S.h2)}">${parseInline(text)}</h2>`;
  },
  makeH2: (text, parseInline, S) => `<h2 style="${escape(S.h2)}">${parseInline(text)}</h2>`,
  makeH3: (text, parseInline, S) => `<h3 style="${escape(S.h3)}">${parseInline(text)}</h3>`,
}};
const body = renderMarkdown(data.markdown, preset);
const title = `<h1 style="${escape(styles.h1)}">${escape(data.title)}</h1>`;
const content = title + body;
fs.writeFileSync(path.join(out, 'wechat-article-text-check.html'), content, 'utf8');
// The banner is outside the article and excluded only from the upstream text comparison.
const banner = '<aside data-role="decoration" style="font:14px/1.6 system-ui;color:#666;border-bottom:1px solid #aaa;padding:12px 0;">排版待审稿 · 作者尚未确认 · 未发布</aside>';
const csp = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-src 'none'";
function preview(dark) {
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="${csp}"><title>${escape(data.title)} · 排版待审</title></head><body style="margin:0;background:${dark ? '#191919' : '#fff'};"><main style="box-sizing:border-box;max-width:720px;margin:0 auto;padding:16px 22px 48px;">${dark ? simulateDark(banner) : banner}<article>${dark ? simulateDark(content) : content}</article></main></body></html>`;
}
for (const [name, text] of [['body', body], ['preview', preview(false)], ['dark-preview', preview(true)]]) {
  fs.writeFileSync(path.join(out, `wechat-article-${name}.html`), text, 'utf8');
}
