/*
 * Telegram Web probe: run inside a web.telegram.org page and read the JSON it returns.
 *
 * It reports which web client is loaded (K or A), whether the user is logged in, which chat is
 * open, the first visible chats, the last visible messages, and which hint selectors matched.
 * When Telegram changes its markup, the "matched" map shows which hints went stale.
 *
 * It only READS the page. It never clicks, types or sends anything, and it never reads login
 * codes. Message text is truncated to keep private content out of logs.
 *
 * Playwright:   const info = await page.evaluate(fs.readFileSync('web_probe.js', 'utf8'));
 * DevTools:     paste the file into the console.
 * Puppeteer:    await page.evaluate(src)
 */
(() => {
  const q = (sel) => document.querySelector(sel);
  const qa = (sel) => Array.from(document.querySelectorAll(sel));
  const text = (el, n = 80) => (el ? (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, n) : null);
  const first = (sels) => { for (const s of sels) { if (q(s)) return s; } return null; };

  const path = location.pathname;
  const version = path.startsWith('/k') ? 'K' : path.startsWith('/a') ? 'A'
    : (q('#column-left') ? 'K' : q('#LeftColumn') ? 'A' : 'unknown');

  const H = {
    K: {
      chatList: ['a.chatlist-chat', '.chatlist .chatlist-chat', '[data-peer-id].row'],
      header: ['.chat-info .peer-title', '#column-center .top .peer-title', '.chat-info'],
      composer: ['.input-message-input[contenteditable="true"]', '#column-center [contenteditable="true"]'],
      messages: ['.bubble[data-mid]', '.bubbles .bubble'],
      login: ['.page-signQR', '.page-sign', '.page-authCode', '.page-password', '.page-signUp'],
      search: ['.input-search input', '#column-left input[type="text"]'],
      out: (el) => el.classList.contains('is-out'),
      peer: (el) => el.getAttribute('data-peer-id'),
    },
    A: {
      chatList: ['.chat-list .ListItem.Chat', '#LeftColumn .ListItem.Chat', '#LeftColumn .chat-item-clickable'],
      header: ['#MiddleColumn .MiddleHeader .fullName', '#MiddleColumn .MiddleHeader h3', '#MiddleColumn .MiddleHeader'],
      composer: ['#editable-message-text', '#MiddleColumn [contenteditable="true"]'],
      messages: ['.Message[data-message-id]', '.messages-container .Message'],
      login: ['#auth-qr-form', '#auth-phone-number-form', '#auth-code-form', '#auth-password-form', '#auth-registration-form'],
      search: ['#telegram-search-input', '#LeftColumn input[type="text"]'],
      out: (el) => el.classList.contains('own'),
      peer: (el) => { const a = el.querySelector('a[href^="#"]'); return a ? a.getAttribute('href').slice(1) : null; },
    },
  };
  const h = H[version];
  if (!h) return JSON.stringify({ version, url: location.href, note: 'Not a recognised Telegram Web client page.' });

  const matched = {};
  for (const k of ['chatList', 'header', 'composer', 'messages', 'login', 'search']) matched[k] = first(h[k]);

  const loginStep = matched.login ? matched.login.replace(/^[.#]/, '') : null;
  const loggedIn = !loginStep && !!matched.chatList;

  const chats = matched.chatList ? qa(matched.chatList).slice(0, 15).map((el) => ({
    peer: h.peer(el),
    title: text(el.querySelector('.peer-title, .fullName, h3, .title'), 60),
    unread: text(el.querySelector('.badge-unread, .ChatBadge, .dialog-subtitle-badge'), 6),
  })) : [];

  const messages = matched.messages ? qa(matched.messages).slice(-10).map((el) => ({
    id: el.getAttribute('data-mid') || el.getAttribute('data-message-id') || el.id || null,
    out: h.out(el),
    text: text(el.querySelector('.message, .text-content, .translatable-message') || el, 120),
  })) : [];

  return JSON.stringify({
    version,
    url: location.href,
    loggedIn,
    loginStep,                       // e.g. "page-signQR" / "auth-code-form": let the user finish login
    openChat: matched.header ? text(q(matched.header), 80) : null,
    composerFound: !!matched.composer,
    chats,
    messages,
    matched,                         // null entries mean that hint is stale: fall back to roles and text
  }, null, 2);
})();
