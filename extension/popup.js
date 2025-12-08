// popup.js - updated to include article image URLs in the payload before sending to backend

function esc(s){ if(!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// promisified sendMessage to active tab
function sendMessageToActiveTab(message) {
  return new Promise((resolve, reject) => {
    chrome.tabs.query({active:true, currentWindow:true}, (tabs) => {
      if (!tabs || !tabs[0]) return reject(new Error('No active tab'));
      chrome.tabs.sendMessage(tabs[0].id, message, (resp) => {
        if (chrome.runtime.lastError) {
          // content script may not be injected or has error
          return reject(new Error(chrome.runtime.lastError.message));
        }
        resolve({resp, tab: tabs[0]});
      });
    });
  });
}

document.getElementById('checkBtn').addEventListener('click', async ()=>{
  const statusEl = document.getElementById('status');
  const resultEl = document.getElementById('result');
  resultEl.innerText = '';
  statusEl.innerText = 'Extracting article...';

  try {
    // 1) extract article (title/body) using content script
    const { resp: extractResp, tab } = await sendMessageToActiveTab({ action: 'extract' });
    if (!extractResp) {
      statusEl.innerText = 'Could not extract article from page.';
      return;
    }

    // 2) request prioritized article images from content script
    statusEl.innerText = 'Fetching images from page...';
    let images = [];
    try {
      const { resp: imgResp } = await sendMessageToActiveTab({ action: 'getImages', limit: 12 });
      if (imgResp && imgResp.images) images = imgResp.images;
    } catch (imgErr) {
      // Non-fatal: continue without images (backend can try fetch URLs if you send none)
      console.warn('Failed to get images from page:', imgErr);
      images = [];
    }

    // Build payload: include extracted article data and image URLs (if any)
    const payload = Object.assign({}, extractResp);
    // normalize image list to array of src strings (include data: URIs too)
    payload.image_urls = (images || []).map(i => i && i.src ? i.src : i).filter(Boolean);

    statusEl.innerText = `Sending article (+${payload.image_urls.length} images) to backend for analysis...`;

    // 3) POST to backend
    const backendUrl = 'http://127.0.0.1:5000/analyze';
    const res = await fetch(backendUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const txt = await res.text().catch(()=>'<no body>');
      throw new Error(`Backend ${res.status}: ${txt}`);
    }

    const json = await res.json();
    statusEl.innerText = 'Analysis complete.';

    // 4) render results (keeps your existing formatting)
    if (json.error) {
      resultEl.innerText = json.error;
      return;
    }

    const t = json.text_report || {};
    const imgs = json.image_report || [];

    let html = '';
    if (t && Object.keys(t).length) {
      html += `<div><b>Similarity (${esc(t.method||'') || 'N/A'}):</b> ${esc(t.similarity||'N/A')} - ${t.is_misleading?'<span style="color:red">Misleading</span>':'<span style="color:green">OK</span>'}</div>`;
      html += `<div style="margin-top:6px"><b>Suggested:</b> ${esc(t.suggested_title || '')}</div>`;
    } else {
      html += `<div><b>Text analysis:</b> No text report returned.</div>`;
    }

    if (imgs && imgs.length) {
      html += '<hr/><div><b>Image reports:</b></div>';
      imgs.forEach(i=>{
        html += `<div class="img-row">`;
        html += `<div class="small"><b>Image:</b> ${esc(i.image)}</div>`;
        html += `<div class="small"><b>Status:</b> ${esc(i.status || 'unknown')}</div>`;
        html += `<div class="small"><b>Reasons:</b> ${esc((i.reasons||[]).join(', ')||'None')}</div>`;
        html += `</div>`;
      });
    } else {
      html += '<div style="margin-top:8px"><i>No image reports returned by backend.</i></div>';
    }

    html += '<hr/>';
    html += '<button id="injectBtn">Inject suggested headline into page</button>';
    resultEl.innerHTML = html;

    // attach inject button (sends injectRewrite message)
    document.getElementById('injectBtn').addEventListener('click', ()=>{
      const suggested = (t && t.suggested_title) ? t.suggested_title : '';
      chrome.tabs.sendMessage(tab.id, { action: 'injectRewrite', suggested_title: suggested }, ()=>{});
    });

  } catch (err) {
    const msg = err && err.message ? err.message : String(err);
    document.getElementById('status').innerText = 'Error: ' + msg;
    document.getElementById('result').innerText = '';
    console.error(err);
  }
});
