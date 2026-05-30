

console.log('nc content script loaded (reuters-tuned extractor)');


const BOILERPLATE_PATTERNS = [
  /At\s+TOI\s+World\s+Desk/i,
  /About\s+the\s+Author/i,
  /Our\s+dedicated\s+team\s+of\s+seasoned\s+journalists/i,
  /Join\s+us\s+on/i,
  /Follow\s+us\s+on/i,
  /Subscribe/i,
  /Read\s+more[:]?/i,
  /Sign\s+up\s+for/i,
  /Stay\s+updated/i,
  /^By\s+[A-Z]/i,
  /Reporting\s+by\b/i,
  /^Reporting\s+by\s+.+;?\s*Editing\s+by\s+/i,
  /Our\s+Standards:/i,
  /Purchase\s+Licensing\s+Rights/i,
  /Suggested\s+Topics/i,
  /Read\s+Next/i,
  /Sign\s+up\s+here/i
];

const KNOWN_WIDGET_CLASSES = /(trc|taboola|mgid|cpl-ad|cpl-|play|promo|promoted|subscribe|newsletter|advert|adunit|ad-|sponsor|social|widget|author|byline|profile|breadcrumb|related|recommended|most-read)/i;

const SITE_RULES = {
  'reuters.com': {},
  'www.reuters.com': {}
};


const reutersRules = {
  title: [
    'article h1',
    'div[data-testid="story-hero"] h1',
    'h1[data-testid="Heading"]',
    'h1[class*="Headline"]',
    'h1[itemprop="headline"]',
    'h1',
    'meta[property="og:title"]'
  ],
  body: [
    'article',
    'div[data-testid="article-body"]',
    'div[data-component="ArticleBody"]',
    'div[class*="ArticleBody"]',
    'div[class*="article-body"]',
    'main',
    'section[data-testid="article-body"]',
    // Generic Reuters paragraph blocks (matches paragraph-0, paragraph-1, ... paragraph-N)
    'div[data-testid^="paragraph-"]'
  ],
  image: [
    'article figure img',
    'figure img',
    'div[data-testid="story-hero"] img',
    'div[class*="LeadMedia"] img',
    'div[class*="Image"] img',
    'img.lead-image',
    'meta[property="og:image"]'
  ]
};
SITE_RULES['www.reuters.com'] = Object.assign({}, reutersRules, SITE_RULES['www.reuters.com']);
SITE_RULES['reuters.com'] = Object.assign({}, reutersRules, SITE_RULES['reuters.com']);



function textOf(el) {
  try { return el && el.innerText ? el.innerText.replace(/\s+/g,' ').trim() : ''; } catch(e) { return ''; }
}
function nodeTextLength(el) { return (textOf(el) || '').length; }
function pCount(el) { try { return el ? el.querySelectorAll('p').length : 0; } catch(e){ return 0; } }
function imageCount(el) { try { return el ? el.querySelectorAll('img').length : 0; } catch(e){ return 0; } }
function linkDensity(el) {
  try {
    if (!el) return 0;
    const text = textOf(el);
    const linksText = Array.from((el.querySelectorAll ? el.querySelectorAll('a') : [])).map(a => a.innerText || '').join(' ');
    if (!text) return 0;
    return (linksText.length / Math.max(1,text.length));
  } catch (e) { return 0; }
}
function getCssSelector(el) {
  if (!el || !el.tagName) return '';
  try {
    let path = [];
    let node = el;
    while (node && node.nodeType === 1 && node !== document.body && node !== document.documentElement) {
      let sel = node.tagName.toLowerCase();
      if (node.id) sel += '#' + node.id;
      else {
        const cls = (node.className || '').toString().trim().split(/\s+/).filter(Boolean);
        if (cls.length) sel += '.' + cls.join('.');
        const siblings = node.parentNode ? Array.from(node.parentNode.children).filter(c => c.tagName === node.tagName) : [];
        if (siblings.length > 1) {
          const idx = Array.prototype.indexOf.call(node.parentNode.children, node) + 1;
          sel += `:nth-child(${idx})`;
        }
      }
      path.unshift(sel);
      node = node.parentNode;
    }
    return path.join(' > ');
  } catch(e){ return ''; }
}

function firstMatch(selectors) {
  if (!selectors) return null;
  for (const s of selectors) {
    if (!s) continue;
    try {
      
      const node = document.querySelector(s);
      if (node) return node;
      
      if (/^meta/i.test(s)) {
        const metas = document.getElementsByTagName('meta');
        for (const m of metas) {
          
          if ((m.getAttribute('property') || '').toLowerCase().indexOf('og:title') !== -1 ||
              (m.getAttribute('name') || '').toLowerCase().indexOf('twitter:title') !== -1 ||
              (m.getAttribute('name') || '').toLowerCase().indexOf('title') !== -1) {
            return m;
          }
        }
      }
    } catch(e){}
  }
  return null;
}

function hasExcludedAncestor(el) {
  if (!el) return false;
  let node = el;
  while (node && node !== document.documentElement) {
    const tag = node.tagName ? node.tagName.toUpperCase() : '';
    if (['ASIDE','NAV','FOOTER','HEADER','FORM'].includes(tag)) return true;
    const cls = (node.className || '').toString();
    const id = (node.id || '').toString();
    if (KNOWN_WIDGET_CLASSES.test(cls) || KNOWN_WIDGET_CLASSES.test(id)) return true;
    node = node.parentElement;
  }
  return false;
}

function isBoilerplate(text) {
  if (!text) return false;
  for (const re of BOILERPLATE_PATTERNS) if (re.test(text)) return true;
  
  if (/^Reporting by\b/i.test(text) || /^Our Standards:/i.test(text)) return true;
  return false;
}

function isAdOrWidget(el) {
  if (!el) return false;
  if (el.tagName && el.tagName.toUpperCase() === 'IFRAME') return true;
  const cls = (el.className || '') + ' ' + (el.id || '');
  return KNOWN_WIDGET_CLASSES.test(cls);
}



function findBodyCandidates(limit = 12) {
  const candidates = [];
  const host = location.hostname.replace(/^www\./,'');
  const rules = SITE_RULES[host] || null;
  const bodySelectors = (rules && rules.body && Array.isArray(rules.body)) ? rules.body.slice() : ['article', 'main', 'div[class*="article"]', 'section', 'div[id*="article"]', 'div[class*="ArticleBody"]'];

  try {
    for (const sel of bodySelectors) {
      if (!sel) continue;
      const el = firstMatch([sel]);
      if (!el) continue;
      if (hasExcludedAncestor(el)) continue;
      const score = Math.max(0, (nodeTextLength(el) / 2000)) + (pCount(el) * 0.2) + (imageCount(el) * 0.3) - linkDensity(el);
      candidates.push({
        node: el,
        selector: getCssSelector(el),
        score,
        textLen: nodeTextLength(el),
        pCount: pCount(el),
        imageCount: imageCount(el),
        linkDensity: linkDensity(el)
      });
    }

    
    try {
      const anyPara = document.querySelector('[data-testid^="paragraph-"]');
      if (anyPara) {
        const container = anyPara.closest('article, main, section') || anyPara.parentElement;
        if (container && !hasExcludedAncestor(container)) {
          const score = Math.max(1.2, (nodeTextLength(container) / 1800)) + (pCount(container) * 0.25) - linkDensity(container) + (imageCount(container) * 0.25);
          candidates.push({
            node: container,
            selector: getCssSelector(container) || '[data-testid^="paragraph-..."]',
            score,
            textLen: nodeTextLength(container),
            pCount: pCount(container),
            imageCount: imageCount(container),
            linkDensity: linkDensity(container)
          });
        }
      }
    } catch(e){ /* ignore */ }

    
    const divs = Array.from(document.querySelectorAll('div, main, article, section')).slice(0, 900);
    for (const el of divs) {
      try {
        if (!el || hasExcludedAncestor(el)) continue;
        const tlen = nodeTextLength(el);
        if (tlen < 180) continue;
        const score = (tlen / 2000) + (pCount(el)*0.12) + (imageCount(el)*0.4) - linkDensity(el);
        candidates.push({ node: el, selector: getCssSelector(el), score, textLen: tlen, pCount: pCount(el), imageCount: imageCount(el), linkDensity: linkDensity(el) });
      } catch(e){}
    }
  } catch(e){}

  candidates.sort((a,b)=>b.score - a.score);
  return candidates.slice(0, limit);
}

function findHeadingCandidates(bodyEl) {
  const candidates = [];
  const meta = (document.querySelector('meta[property="og:title"]') || document.querySelector('meta[name="twitter:title"]') || document.querySelector('meta[name="title"]'));
  if (meta && meta.content) {
    candidates.push({ node: meta, selector: 'meta:title', text: meta.content.trim(), score: 2.5, reason: 'meta' });
  }
  if (document.title) {
    candidates.push({ node: null, selector: 'document.title', text: document.title.trim(), score: 1.6, reason: 'document.title' });
  }

  const host = location.hostname.replace(/^www\./,'');
  const rules = SITE_RULES[host] || null;
  const titleSelList = (rules && rules.title && Array.isArray(rules.title)) ? rules.title : ['article h1','h1[data-testid="Heading"]','h1[itemprop="headline"]','h1','meta[property="og:title"]'];

  for (const sel of titleSelList) {
    try {
      const n = firstMatch([sel]);
      if (!n) continue;
      if (n.tagName && n.tagName.toLowerCase() === 'meta') {
        const c = n.getAttribute('content') || n.content || '';
        if (c) candidates.push({ node: n, selector: sel, text: c.trim(), score: 2.6, reason: 'meta' });
        continue;
      }
      const t = textOf(n);
      if (!t || t.length < 6) continue;
      if (hasExcludedAncestor(n)) continue;
      candidates.push({ node: n, selector: getCssSelector(n), text: t.trim(), score: Math.min(3.0, Math.max(0.8, t.length/30)), reason: 'node' });
    } catch(e){}
  }

  
  try {
    const within = bodyEl || document;
    ['h1','h2','h3'].forEach(tag => {
      const nodes = Array.from(within.querySelectorAll(tag));
      nodes.forEach(n=>{
        const t = textOf(n);
        if (!t || t.length < 6) return;
        if (hasExcludedAncestor(n)) return;
        candidates.push({ node: n, selector: getCssSelector(n), text: t.trim(), score: Math.min(2.8, t.length/20), reason: 'fallback' });
      });
    });
  } catch(e){}

  
  const keyed = {};
  const uniq = [];
  for (const c of candidates) {
    const k = (c.text || '').slice(0,140);
    if (!k) continue;
    if (!keyed[k]) { keyed[k] = true; uniq.push(c); }
  }
  uniq.sort((a,b)=>b.score - a.score);
  return uniq;
}


function getBestTitleNode() {
  const host = location.hostname.replace(/^www\./,'');
  const rules = SITE_RULES[host] || null;
  const candidates = (rules && rules.title && Array.isArray(rules.title)) ? rules.title : ['article h1','h1[data-testid="Heading"]','h1[itemprop="headline"]','h1','meta[property="og:title"]'];

  for (const sel of candidates) {
    const node = firstMatch([sel]);
    if (!node) continue;
    if (node.tagName && node.tagName.toLowerCase() === 'meta') {
      const c = node.getAttribute('content') || node.content || '';
      if (c) return { _meta: true, content: c, selector: sel };
      continue;
    }
    try {
      const t = textOf(node);
      if (!t || t.length < 6) continue;
      return node;
    } catch(e){}
  }
  return null;
}

function getBestBodyNode() {
  const candidates = findBodyCandidates(18);
  if (!candidates || !candidates.length) return null;
  return candidates[0].node || null;
}


function endsWithSentenceStop(text) {
  return /[.!?]["']?\s*$/.test((text || '').trim());
}

function mergeLeadingParagraphsUntilStop(paras) {
  if (!paras || !paras.length) return paras;
  if (endsWithSentenceStop(paras[0])) return paras;
  let merged = paras[0];
  let i = 1;
  while (i < paras.length && !endsWithSentenceStop(merged)) {
    merged = (merged + ' ' + paras[i]).trim();
    i++;
  }
  return [merged, ...paras.slice(i)];
}

function extractArticleData() {
  const data = { title: '', paragraphs: '', image: '', titleSelector: '', bodySelector: '' };

  const tnode = getBestTitleNode();
  if (tnode) {
    if (tnode._meta) {
      data.title = (tnode.content || '').toString().trim();
      data.titleSelector = tnode.selector || 'meta';
    } else {
      data.title = textOf(tnode) || '';
      data.titleSelector = getCssSelector(tnode) || '';
    }
  } else {
    data.title = document.title || '';
    data.titleSelector = 'document.title';
  }

  
  let paras = [];
  try {
    const paraNodes = Array.from(document.querySelectorAll('div[data-testid^="paragraph-"], [data-testid^="paragraph-"]'));
    if (paraNodes && paraNodes.length) {
      paras = paraNodes
        .filter(p => p && (p.innerText || '').trim().length > 20)
        .filter(p => !hasExcludedAncestor(p) && !isAdOrWidget(p))
        .map(p => (p.innerText || '').trim())
        .filter(t => !isBoilerplate(t));
      const firstPara = paraNodes[0];
      const container = firstPara ? (firstPara.closest('article, main, section') || firstPara.parentElement) : null;
      data.bodySelector = container ? getCssSelector(container) : 'data-testid-paragraphs';
    }
  } catch(e){ paras = []; }

  
  if (!paras || paras.length === 0) {
    const bodyNode = getBestBodyNode();
    if (bodyNode) {
      paras = Array.from(bodyNode.querySelectorAll('p'))
        .filter(p => p && p.innerText && p.innerText.trim().length > 30)
        .filter(p => !hasExcludedAncestor(p) && !isAdOrWidget(p))
        .map(p => p.innerText.trim())
        .filter(t => !isBoilerplate(t));
      data.bodySelector = getCssSelector(bodyNode);
    } else {
      paras = Array.from(document.querySelectorAll('body p'))
        .filter(p => p && p.innerText && p.innerText.trim().length > 40)
        .filter(p => !hasExcludedAncestor(p) && !isAdOrWidget(p))
        .map(p => p.innerText.trim())
        .filter(t => !isBoilerplate(t));
      data.bodySelector = 'body';
    }
  }

  
  while (paras.length && isBoilerplate(paras[paras.length - 1])) paras.pop();

  paras = mergeLeadingParagraphsUntilStop(paras);

  data.paragraphs = paras.join('\n\n');

  
  try {
    const host = location.hostname.replace(/^www\./,'');
    const rules = SITE_RULES[host] || null;
    const imgSelectors = (rules && rules.image && Array.isArray(rules.image)) ? rules.image : ['article figure img','figure img','img.lead-image','meta[property="og:image"]'];
    for (const sel of imgSelectors) {
      try {
        const n = firstMatch([sel]);
        if (!n) continue;
        if (n.tagName && n.tagName.toLowerCase() === 'meta') {
          const c = n.getAttribute('content') || n.content || '';
          if (c) { data.image = c; break; }
        } else {
          const src = n.getAttribute('src') || n.getAttribute('data-src') || n.src || '';
          if (src) { data.image = src; break; }
        }
      } catch(e){}
    }
    if (!data.image) {
      
      const imgs = Array.from(document.querySelectorAll('img')).filter(im => im && (im.naturalWidth || im.width));
      imgs.sort((a,b) => ((b.naturalWidth||b.width||0)*(b.naturalHeight||b.height||0)) - ((a.naturalWidth||a.width||0)*(a.naturalHeight||a.height||0)));
      for (const im of imgs) {
        if (hasExcludedAncestor(im)) continue;
        
        if (im.closest('article') || im.closest('main') || im.closest('[data-testid="story-hero"]')) {
          data.image = im.getAttribute('src') || im.getAttribute('data-src') || im.src || '';
          if (data.image) break;
        }
      }
    }
  } catch(e){}

  return data;
}


function absUrl(src) {
  if (!src) return '';
  try { return new URL(src, location.href).href; } catch (e) { return src; }
}

function isNonPhotoSrc(src) {
  const s = (src || '').toLowerCase();
  if (!s || s.endsWith('.svg') || s.includes('.svg?')) return true;
  if (/(logo|footer|favicon|sprite|avatar|\/icon)/i.test(s)) return true;
  return false;
}

function gatherImageList(limit = 12) {
  const imgs = Array.from(document.querySelectorAll('img')).map(im => {
    const raw = im.getAttribute('src') || im.getAttribute('data-src') || im.src || '';
    const src = absUrl(raw);
    if (!src || isNonPhotoSrc(src)) return null;
    return {
      src,
      width: im.naturalWidth || im.width || 0,
      height: im.naturalHeight || im.height || 0
    };
  }).filter(i => i && i.src);
  
  const seen = new Set();
  const uniq = [];
  for (const i of imgs) {
    if (!seen.has(i.src)) { seen.add(i.src); uniq.push(i); }
    if (uniq.length >= limit) break;
  }
  return uniq;
}


function saveOriginalTitle(node) {
  if (!node) return false;
  try {
    if (!node.__nc_originalText) node.__nc_originalText = node.innerHTML;
    return true;
  } catch(e){ return false; }
}

function replaceElementText(el, newTextOrHtml) {
  try {
    if (!el) return false;
    saveOriginalTitle(el);
    if (/<[^>]+>/.test(newTextOrHtml)) el.innerHTML = newTextOrHtml;
    else el.innerText = newTextOrHtml;
    try {
      el.style.transition = 'box-shadow 280ms ease';
      el.style.boxShadow = '0 0 0 4px rgba(255,200,0,0.25)';
      setTimeout(()=> { if (el && el.style) el.style.boxShadow = ''; }, 1400);
    } catch(e){}
    return true;
  } catch(e){ console.error('nc replaceElementText', e); return false; }
}

function replaceTitleInPlace(newTextOrHtml) {
  if (!newTextOrHtml || typeof newTextOrHtml !== 'string') return false;
  const tnode = getBestTitleNode();
  if (!tnode) return false;

  if (tnode._meta) {
    
    const fallback = document.querySelector('article h1') || document.querySelector('h1') || document.querySelector('h2') || document.querySelector('[data-testid="Heading"]') || document.querySelector('[data-component="ArticleHeadline"]');
    if (!fallback) {
      console.warn('nc: meta title found but no H1/H2 to replace; aborting replacement.');
      return false;
    }
    return replaceElementText(fallback, newTextOrHtml);
  }

  
  try {
    return replaceElementText(tnode, newTextOrHtml);
  } catch(e){ console.error('nc replaceTitleInPlace error', e); return false; }
}

function injectRewriteBanner(s) {
  try {
    const existing = document.getElementById('nc-banner');
    if (existing) existing.remove();
    const banner = document.createElement('div');
    banner.id = 'nc-banner';
    banner.style.position = 'fixed';
    banner.style.top = '0';
    banner.style.left = '0';
    banner.style.right = '0';
    banner.style.zIndex = 2147483647;
    banner.style.background = '#fffbe6';
    banner.style.padding = '10px 16px';
    banner.style.borderBottom = '1px solid rgba(0,0,0,0.08)';
    banner.innerHTML = '<strong>Injected headline:</strong> ' + (s ? s.replace(/</g,'&lt;') : '');
    const close = document.createElement('button');
    close.innerText = 'Close';
    close.style.marginLeft = '12px';
    close.onclick = ()=> banner.remove();
    banner.appendChild(close);
    document.documentElement.appendChild(banner);
    return true;
  } catch(e){ console.error('nc: injectRewriteBanner failed', e); return false; }
}


chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
  try {
    if (!msg || !msg.action) { sendResponse(null); return true; }

    
    if (msg.action === 'extract') {
      const d = extractArticleData();
      
      sendResponse(d);
      return true;
    }

    
    if (msg.action === 'getImages') {
      const limit = (msg.limit && Number(msg.limit)) ? Number(msg.limit) : 12;
      const images = gatherImageList(limit);
      sendResponse({ images });
      return true;
    }

    
    if (msg.action === 'injectRewrite') {
      const suggested = (msg.suggested_title || msg.title || msg.payload || '').toString();
      let ok = false;
      try {
        ok = replaceTitleInPlace(suggested);
      } catch(e){ ok = false; }
      if (!ok) {
        
        try { injectRewriteBanner(suggested); ok = true; } catch(e){ ok = false; }
      }
      sendResponse({ ok });
      return true;
    }

    
    if (msg.action === 'getArticleData') {
      sendResponse(extractArticleData());
      return true;
    }

    
    if (msg.action === 'debugScan') {
      const bodies = findBodyCandidates(12);
      const heads = findHeadingCandidates();
      sendResponse({ bodies: bodies.map(b=>({selector:b.selector,score:b.score,pCount:b.pCount,textLen:b.textLen})), heads: heads.map(h=>({selector:h.selector,text:h.text? h.text.slice(0,200):'',score:h.score,reason:h.reason})) });
      return true;
    }

    
    sendResponse(null);
    return true;
  } catch(e) {
    console.error('nc message handler error', e);
    try { sendResponse(null); } catch(e){}
    return true;
  }
});


try {
  const d = extractArticleData();
  console.info('nc: extracted article data (title/image/body length):', { title: d.title && d.title.slice(0,200), titleSelector: d.titleSelector, bodySelector: d.bodySelector, bodyLength: d.paragraphs ? d.paragraphs.length : 0 });
} catch (e) {
  console.warn('nc: extractor init failed', e);
}


window.ncDebugScan = function() {
  try {
    const bodies = findBodyCandidates(15);
    console.log('ncDebugScan: top body candidates (selector,score,pCount,textLen,imageCount):');
    bodies.forEach(b => console.log(b.selector, b.score.toFixed(2), b.pCount, b.textLen, b.imageCount));
    const heads = findHeadingCandidates();
    console.log('ncDebugScan: top heading candidates (selector,score,reason,text):');
    heads.forEach(h => console.log(h.selector || '(meta)', h.score.toFixed(2), h.reason, h.text? h.text.slice(0,200):''));
    const data = extractArticleData();
    console.log('ncDebugScan: chosen title/body:', data.titleSelector, data.bodySelector);
    return { bodies, heads, data };
  } catch(e) { console.warn('ncDebugScan failed', e); return null; }
};

window.__nc_getBestTitleNode = getBestTitleNode;
window.__nc_replaceTitleInPlace = replaceTitleInPlace;
