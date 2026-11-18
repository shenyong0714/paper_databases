// ==UserScript==
// @name         Research Desk → Claude (Paper Desk chat)
// @namespace    shenyong0714.research-desk
// @version      1.2.0
// @description  When Research Desk opens the Paper Desk chat with ?rd=<arXiv id>, put that paper (abstract, figure captions, full text) into the message box. You still press Send.
// @match        https://claude.ai/*
// @grant        GM_getValue
// @grant        GM_setValue
// @run-at       document-idle
// @downloadURL  https://shenyong0714.github.io/paper_databases/userscript/research-desk-claude.user.js
// @updateURL    https://shenyong0714.github.io/paper_databases/userscript/research-desk-claude.user.js
// ==/UserScript==

(function () {
  'use strict';

  // The desk's database only answers its signed-in owner. This script reads one paper at a
  // time through ask_paper() with a separate Ask key, asked for once and kept in the script's storage.
  const SUPABASE_URL = 'https://aleirqepbpkelpujixrb.supabase.co';
  const ANON = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFsZWlycWVwYnBrZWxwdWppeHJiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTQ4ODY1NjUsImV4cCI6MjExMDQ2MjU2NX0.XZVVIvRo7CeZhnzTSXgPLfV28GBVrI1B5jwByEym6Zg';

  const params = new URLSearchParams(location.search);
  const id = params.get('rd');
  if (!id) return;
  const isArxiv = /^\d{4}\.\d{4,5}$/.test(id);
  if (!isArxiv && !/^doi:10\.\d{4,9}\/\S+$/.test(id)) { toast(`Research Desk: "${id}" is not a paper id`, true); return; }

  // drop ?rd= so a reload doesn't insert the paper twice
  params.delete('rd');
  history.replaceState(null, '', location.pathname + (params.toString() ? '?' + params : '') + location.hash);

  run().catch(e => toast('Research Desk: ' + e.message, true));

  async function run() {
    toast(`Research Desk: loading ${id}…`);
    const { paper, text } = await askPaper(id);
    const msg = buildPrompt(paper, text);
    const ed = await waitFor(() => document.querySelector('div.ProseMirror[contenteditable="true"]'), 20000);
    if (!ed) throw new Error('message box not found (are you signed in?)');
    insert(ed, msg);
    toast(text ? `${id} added with full text. Press Send.` : `${id} added (abstract only). Press Send.`);
  }

  function askKey(force) {
    // Tampermonkey storage when available (Safari's Userscripts lacks the GM_ API): fall back to localStorage
    const get = () => (typeof GM_getValue === 'function' ? GM_getValue('askKey', '') : localStorage.getItem('rdAskKey') || '');
    const set = (v) => (typeof GM_setValue === 'function' ? GM_setValue('askKey', v) : localStorage.setItem('rdAskKey', v));
    let k = get();
    if (!k || force) {
      k = (prompt(force ? 'Research Desk: that Ask key was not accepted. Paste the Ask key again:'
                        : 'Research Desk: paste your Ask key (asked once on this browser):') || '').trim();
      if (!k) throw new Error('no Ask key');
      set(k);
    }
    return k;
  }
  async function askPaper(id, retry) {
    const r = await fetch(`${SUPABASE_URL}/rest/v1/rpc/ask_paper`, {
      method: 'POST',
      headers: { apikey: ANON, Authorization: `Bearer ${ANON}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ p_id: id, p_key: askKey(retry) }),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      if (/invalid key/.test(body.message || '') && !retry) return askPaper(id, true);
      throw new Error(body.message || `database ${r.status}`);
    }
    if (!body.paper) throw new Error(`${id} is not in Research Desk`);
    return { paper: body.paper, text: body.text || '' };
  }

  function buildPrompt(p, full) {
    const caps = (p.figures || []).map(x => `- Fig. ${x.n} (p${x.page}): ${x.caption}`).join('\n');
    return [
      `New paper for my Paper Desk. Read it, keep it in mind alongside the other papers in this chat, then answer my questions.`,
      ``,
      `Title: ${p.title}`,
      /^\d{4}\.\d{4,5}$/.test(p.arxiv_id) ? `arXiv: https://arxiv.org/abs/${p.arxiv_id}  (${p.cat || ''})`
                                         : `Link: ${p.url || 'https://doi.org/' + p.doi}`,
      p.journal ? `Published: ${p.journal}${p.year ? ' ' + p.year : ''}${p.doi ? '  doi:' + p.doi : ''}` : '',
      `Authors: ${(p.authors || []).join(', ')}`,
      `Matched keywords: ${(p.matched || []).join(', ')}`,
      ``,
      `Abstract:`, p.abstract || '',
      caps ? `\nFigure captions:\n${caps}` : '',
      full ? `\n===== FULL TEXT =====\n${full}` : `\n(Full text not available here; use the link above.)`,
    ].join('\n');
  }

  function insert(ed, msg) {
    ed.focus();
    const before = ed.innerText.length;
    // a paste event lets claude.ai handle long text the way it handles a normal paste
    try {
      const dt = new DataTransfer();
      dt.setData('text/plain', msg);
      ed.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
    } catch (_) { /* fall through */ }
    setTimeout(() => {
      const pasted = ed.innerText.length > before ||
        document.querySelector('[data-testid*="file-thumbnail"], [data-testid*="attachment"]');
      if (!pasted) {
        ed.focus();
        document.execCommand('insertText', false, msg);
      }
    }, 600);
  }

  function waitFor(fn, ms) {
    return new Promise(res => {
      const t0 = Date.now();
      (function tick() {
        const v = fn();
        if (v || Date.now() - t0 > ms) return res(v || null);
        setTimeout(tick, 250);
      })();
    });
  }

  function toast(text, bad) {
    let el = document.getElementById('rd-toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'rd-toast';
      el.style.cssText = 'position:fixed;left:50%;bottom:90px;transform:translateX(-50%);z-index:99999;' +
        'padding:9px 15px;border-radius:6px;font:13px system-ui,sans-serif;box-shadow:0 4px 18px rgba(0,0,0,.25)';
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.style.background = bad ? '#b42318' : '#1f2328';
    el.style.color = '#fff';
    clearTimeout(el._t);
    el._t = setTimeout(() => el.remove(), bad ? 10000 : 5000);
  }
})();
