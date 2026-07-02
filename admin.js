// ─── INFORMED REPUBLIC — admin.js ──────────────────────────────────────

// ── GitHub config ─────────────────────────────────────────────────────
// Your GitHub Personal Access Token is stored in localStorage under
// 'ir_github_token' and set once via the Settings panel.
const GITHUB_OWNER = 'mraw435';
const GITHUB_REPO  = 'informed-republic';
const GITHUB_FILE  = 'briefs.json';
const GITHUB_API   = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/contents/${GITHUB_FILE}`;

// ── Local storage keys ────────────────────────────────────────────────
const DEFAULT_PASSWORD     = 'republic2024';
const STORAGE_KEY_DRAFTS   = 'ir_drafts';
const STORAGE_KEY_SETTINGS = 'ir_settings';
const STORAGE_KEY_PW       = 'ir_admin_pw';
const STORAGE_KEY_TOKEN    = 'ir_github_token';

// ── Helpers ───────────────────────────────────────────────────────────
function todayKey() {
  return new Date().toISOString().slice(0, 10);
}
function formatDisplayDate(isoDate) {
  const d = new Date(isoDate + 'T12:00:00');
  return d.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
}

// Local draft helpers (working scratchpad only — not shown to visitors)
function getDrafts() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY_DRAFTS) || '{}'); }
  catch { return {}; }
}
function saveDrafts(drafts) {
  localStorage.setItem(STORAGE_KEY_DRAFTS, JSON.stringify(drafts));
}

function getSettings() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY_SETTINGS) || '{}'); }
  catch { return {}; }
}
function saveSettingsToStorage(obj) {
  localStorage.setItem(STORAGE_KEY_SETTINGS, JSON.stringify(obj));
}
function getAdminPw() {
  return localStorage.getItem(STORAGE_KEY_PW) || DEFAULT_PASSWORD;
}
function getGitHubToken() {
  return localStorage.getItem(STORAGE_KEY_TOKEN) || '';
}
function showToast(msg, color) {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.style.borderLeftColor = color || '#8b1a1a';
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3500);
}

// ── GitHub API helpers ────────────────────────────────────────────────
async function fetchBriefsFromGitHub() {
  const token = getGitHubToken();
  const headers = {
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28'
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(GITHUB_API, { headers });
  if (!res.ok) throw new Error(`GitHub fetch failed: ${res.status}`);
  const data = await res.json();
  const content = JSON.parse(atob(data.content.replace(/\n/g, '')));
  return { briefs: content.briefs || [], sha: data.sha };
}

async function pushBriefsToGitHub(briefs, sha, commitMessage) {
  const token = getGitHubToken();
  if (!token) throw new Error('No GitHub token set. Add it in Settings.');

  const content = btoa(unescape(encodeURIComponent(
    JSON.stringify({ briefs }, null, 2)
  )));

  const res = await fetch(GITHUB_API, {
    method: 'PUT',
    headers: {
      'Accept': 'application/vnd.github+json',
      'Authorization': `Bearer ${token}`,
      'X-GitHub-Api-Version': '2022-11-28',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      message: commitMessage,
      content,
      sha
    })
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(`GitHub push failed: ${err.message}`);
  }
  return await res.json();
}

// ── Auth gate ─────────────────────────────────────────────────────────
function checkGate() {
  const pw = document.getElementById('gatePassword').value;
  const hint = document.getElementById('gateHint');
  if (pw === getAdminPw()) {
    document.getElementById('gate').style.display = 'none';
    document.getElementById('adminWrap').style.display = 'grid';
    document.getElementById('statusDot').classList.add('online');
    initAdmin();
  } else {
    hint.textContent = 'Incorrect password.';
    document.getElementById('gatePassword').value = '';
  }
}
document.getElementById('gatePassword').addEventListener('keydown', e => {
  if (e.key === 'Enter') checkGate();
});
function logout() {
  document.getElementById('adminWrap').style.display = 'none';
  document.getElementById('gate').style.display = 'flex';
  document.getElementById('gatePassword').value = '';
  document.getElementById('statusDot').classList.remove('online');
}
function changePassword() {
  const val = document.getElementById('newPassword').value.trim();
  if (!val) { showToast('Password cannot be empty.'); return; }
  localStorage.setItem(STORAGE_KEY_PW, val);
  document.getElementById('newPassword').value = '';
  showToast('✓ Password updated.', '#1e8449');
}

// ── Panel navigation ──────────────────────────────────────────────────
function showPanel(name) {
  document.querySelectorAll('.panel').forEach(p => p.style.display = 'none');
  document.getElementById('panel-' + name).style.display = 'block';
  document.querySelectorAll('.sidebar-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.sidebar-btn').forEach(b => {
    if (b.getAttribute('onclick')?.includes(name)) b.classList.add('active');
  });
  if (name === 'queue') renderQueue();
  if (name === 'archive') renderArchive();
  if (name === 'settings') loadSettings();
}

// ── Admin init ────────────────────────────────────────────────────────
function initAdmin() {
  document.getElementById('genDate').value = todayKey();
  checkExistingDraft();
  renderQueue();
}

function checkExistingDraft() {
  const date = document.getElementById('genDate').value || todayKey();
  const drafts = getDrafts();
  const existing = drafts[date];
  const note = document.getElementById('existingNote');
  if (existing) {
    note.textContent = `A ${existing.status} draft already exists for this date.`;
    if (existing.status === 'pending' || existing.status === 'draft') {
      showExistingDraft(date, existing);
    }
  } else {
    note.textContent = '';
  }
}
document.getElementById('genDate').addEventListener('change', checkExistingDraft);

// ── Generate brief via Anthropic API ─────────────────────────────────
let currentDraftDate = null;
let currentDraftHTML = null;

async function generateBrief() {
  const btn = document.getElementById('generateBtn');
  const progress = document.getElementById('genProgress');
  const draftArea = document.getElementById('draftArea');
  const date = document.getElementById('genDate').value || todayKey();
  const focus = document.getElementById('genFocus').value.trim();
  const tone = document.getElementById('genTone').value.trim();
  const settings = getSettings();

  btn.disabled = true;
  btn.textContent = '⏳ Generating…';
  progress.style.display = 'block';
  draftArea.style.display = 'none';

  const steps = ['step1','step2','step3','step4'];
  steps.forEach(s => {
    const el = document.getElementById(s);
    el.classList.remove('active','done');
  });

  function setStep(i) {
    if (i > 0) {
      document.getElementById(steps[i-1]).classList.remove('active');
      document.getElementById(steps[i-1]).classList.add('done');
    }
    if (i < steps.length) document.getElementById(steps[i]).classList.add('active');
  }

  setStep(0);

  const displayDate = formatDisplayDate(date);
  const styleGuidance = settings.styleGuidance || 'Nonpartisan, clear, factual. Written for an educated general audience interested in how Washington works.';
  const focusNote = focus ? `Pay special attention to: ${focus}.` : '';
  const toneNote = tone ? `Tone: ${tone}.` : '';

  const systemPrompt = `You are the editorial AI for Informed Republic, a nonpartisan civic news site. Your job is to write the Daily Brief — a morning summary of what is happening in Washington D.C. in politics and policy.

Style guidance: ${styleGuidance}
${toneNote}

Format the brief in clean HTML using only: <h3>, <p>, <ul>, <li>, <strong>, <em>. No divs, no classes, no inline styles.

Structure:
- Open with a 2-3 sentence overview of the day's top theme
- Then 3-5 sections, each with an <h3> topic heading and 1-3 <p> or <ul> bullets
- Close with a 1-sentence "What to watch" forward-looking note

Keep the total to ~400-550 words. Be specific — name legislation, committees, members of Congress, dates, vote counts where relevant. Never be partisan. Always present multiple perspectives on contested issues.`;

  const userPrompt = `Write the Daily Brief for ${displayDate}. Search for the most important political and policy news coming out of Washington D.C. today. ${focusNote}

Return only the HTML content of the brief body (no surrounding tags, no markdown fences).`;

  try {
    await delay(600); setStep(1);
    await delay(400); setStep(2);

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'claude-sonnet-4-6',
        max_tokens: 1000,
        system: systemPrompt,
        tools: [{ type: 'web_search_20250305', name: 'web_search' }],
        messages: [{ role: 'user', content: userPrompt }]
      })
    });

    const data = await response.json();
    setStep(3);

    const html = data.content
      .filter(b => b.type === 'text')
      .map(b => b.text)
      .join('')
      .trim()
      .replace(/^```html?\n?/, '')
      .replace(/\n?```$/, '');

    currentDraftDate = date;
    currentDraftHTML = html;

    // Save locally as draft (scratchpad only)
    const drafts = getDrafts();
    drafts[date] = {
      status: 'draft',
      html,
      generatedAt: new Date().toISOString(),
      feedback: ''
    };
    saveDrafts(drafts);

    setStep(4);
    await delay(400);
    showDraft(date, html);

  } catch (err) {
    console.error(err);
    showToast('Error generating brief. Check console.');
  } finally {
    btn.disabled = false;
    btn.textContent = '⚡ Generate Brief';
  }
}

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

function showDraft(date, html) {
  const draftArea = document.getElementById('draftArea');
  document.getElementById('draftDateLabel').textContent = formatDisplayDate(date);
  document.getElementById('draftEditor').innerHTML = html;
  document.getElementById('feedbackBox').value = '';
  draftArea.style.display = 'block';
  draftArea.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function showExistingDraft(date, draft) {
  currentDraftDate = date;
  currentDraftHTML = draft.html;
  document.getElementById('genProgress').style.display = 'none';
  showDraft(date, draft.html);
  document.getElementById('feedbackBox').value = draft.feedback || '';
}

// ── Draft actions ─────────────────────────────────────────────────────
function saveDraft() {
  if (!currentDraftDate) return;
  const html = document.getElementById('draftEditor').innerHTML;
  const feedback = document.getElementById('feedbackBox').value;
  const drafts = getDrafts();
  drafts[currentDraftDate] = {
    ...drafts[currentDraftDate],
    status: 'pending',
    html,
    feedback,
    savedAt: new Date().toISOString()
  };
  saveDrafts(drafts);
  showToast('💾 Draft saved to queue.');
  checkExistingDraft();
}

function rejectDraft() {
  if (!currentDraftDate) return;
  const feedback = document.getElementById('feedbackBox').value;
  const drafts = getDrafts();
  drafts[currentDraftDate] = {
    ...drafts[currentDraftDate],
    status: 'rejected',
    feedback,
    rejectedAt: new Date().toISOString()
  };
  saveDrafts(drafts);
  document.getElementById('draftArea').style.display = 'none';
  document.getElementById('genProgress').style.display = 'none';
  showToast('✕ Brief sent back. Adjust your focus/tone settings and regenerate.', '#c0392b');
  currentDraftDate = null;
  checkExistingDraft();
}

async function reviseDraft() {
  if (!currentDraftDate) return;
  const feedback = document.getElementById('feedbackBox').value.trim();
  if (!feedback) {
    showToast('Add feedback in the notes box first so the AI knows what to change.');
    return;
  }

  const currentHTML = document.getElementById('draftEditor').innerHTML;
  const btn = document.querySelector('.btn-secondary[onclick="reviseDraft()"]');
  btn.disabled = true;
  btn.textContent = '⏳ Revising…';

  const settings = getSettings();
  const styleGuidance = settings.styleGuidance || 'Nonpartisan, clear, factual. Written for an educated general audience interested in how Washington works.';
  const displayDate = formatDisplayDate(currentDraftDate);

  const systemPrompt = `You are the editorial AI for Informed Republic, a nonpartisan civic news site.
Style guidance: ${styleGuidance}
Format the brief in clean HTML using only: <h3>, <p>, <ul>, <li>, <strong>, <em>. No divs, no classes, no inline styles.
Return only the revised HTML content of the brief body (no surrounding tags, no markdown fences).`;

  const userPrompt = `You wrote the following Daily Brief for ${displayDate}:

--- CURRENT DRAFT ---
${currentHTML}
--- END DRAFT ---

The editor has reviewed it and provided this feedback:
"${feedback}"

Please revise the brief incorporating this feedback. Keep it ~400-550 words, nonpartisan, and specific.`;

  try {
    const response = await fetch('/api/generate-brief', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'claude-sonnet-4-6',
        max_tokens: 1000,
        system: systemPrompt,
        messages: [{ role: 'user', content: userPrompt }]
      })
    });

    const data = await response.json();
    const html = data.content
      .filter(b => b.type === 'text')
      .map(b => b.text)
      .join('')
      .trim()
      .replace(/^```html?\n?/, '')
      .replace(/\n?```$/, '');

    document.getElementById('draftEditor').innerHTML = html;
    document.getElementById('feedbackBox').value = '';

    const drafts = getDrafts();
    drafts[currentDraftDate] = {
      ...drafts[currentDraftDate],
      status: 'draft',
      html,
      revisedAt: new Date().toISOString()
    };
    saveDrafts(drafts);

    showToast('✎ Brief revised — review the updated draft.', '#b8860b');

  } catch (err) {
    console.error(err);
    showToast('Error revising brief. Check console.');
  } finally {
    btn.disabled = false;
    btn.textContent = '✎ Revise with Feedback';
  }
}


  if (!currentDraftDate) return;
  const html = document.getElementById('draftEditor').innerHTML;
  const feedback = document.getElementById('feedbackBox').value;
  const btn = document.querySelector('.btn-success');

  btn.disabled = true;
  btn.textContent = '⏳ Publishing…';

  try {
    // Fetch current briefs.json from GitHub (we need the sha to update it)
    showToast('📡 Connecting to GitHub…');
    const { briefs, sha } = await fetchBriefsFromGitHub();

    // Remove any existing entry for this date and add the new one at the top
    const updated = briefs.filter(b => b.date !== currentDraftDate);
    updated.unshift({
      date: currentDraftDate,
      html,
      publishedAt: new Date().toISOString()
    });

    // Push updated briefs.json back to GitHub
    await pushBriefsToGitHub(updated, sha, `Daily Brief: ${currentDraftDate}`);

    // Mark locally as published
    const drafts = getDrafts();
    drafts[currentDraftDate] = {
      ...drafts[currentDraftDate],
      status: 'published',
      html,
      feedback,
      publishedAt: new Date().toISOString()
    };
    saveDrafts(drafts);

    document.getElementById('draftArea').style.display = 'none';
    document.getElementById('genProgress').style.display = 'none';
    showToast('✓ Brief published to GitHub — now live on the homepage!', '#1e8449');
    currentDraftDate = null;
    checkExistingDraft();
    renderQueue();

  } catch (err) {
    console.error(err);
    showToast(`✕ Publish failed: ${err.message}`, '#c0392b');
  } finally {
    btn.disabled = false;
    btn.textContent = '✓ Approve & Publish';
  }
}

// ── Queue ─────────────────────────────────────────────────────────────
function renderQueue() {
  const drafts = getDrafts();
  const list = document.getElementById('queueList');
  const pending = Object.entries(drafts)
    .filter(([,b]) => b.status === 'pending' || b.status === 'draft')
    .sort((a,b) => b[0].localeCompare(a[0]));

  if (!pending.length) {
    list.innerHTML = '<div class="empty-state">No briefs pending review.</div>';
    return;
  }
  list.innerHTML = pending.map(([date, brief]) => `
    <div class="queue-item">
      <span class="queue-item-date">${formatDisplayDate(date)}</span>
      <span class="queue-item-preview">${stripHTML(brief.html).slice(0,120)}…</span>
      <div class="queue-item-actions">
        <span class="status-badge status-${brief.status}">${brief.status}</span>
        <button class="btn-secondary btn-sm" onclick="reviewFromQueue('${date}')">Review</button>
        <button class="btn-success btn-sm" onclick="quickPublish('${date}')">Publish</button>
      </div>
    </div>
  `).join('');
}

function reviewFromQueue(date) {
  const drafts = getDrafts();
  const draft = drafts[date];
  if (!draft) return;
  showPanel('generate');
  document.getElementById('genDate').value = date;
  currentDraftDate = date;
  currentDraftHTML = draft.html;
  document.getElementById('genProgress').style.display = 'none';
  showDraft(date, draft.html);
  document.getElementById('feedbackBox').value = draft.feedback || '';
}

async function quickPublish(date) {
  const drafts = getDrafts();
  if (!drafts[date]) return;
  currentDraftDate = date;
  document.getElementById('draftEditor').innerHTML = drafts[date].html;
  await publishBrief();
}

// ── Archive ───────────────────────────────────────────────────────────
async function renderArchive() {
  const list = document.getElementById('archiveList');
  list.innerHTML = '<div class="empty-state">Loading archive from GitHub…</div>';
  try {
    const { briefs } = await fetchBriefsFromGitHub();
    if (!briefs.length) {
      list.innerHTML = '<div class="empty-state">No published briefs yet.</div>';
      return;
    }
    const sorted = [...briefs].sort((a,b) => b.date.localeCompare(a.date));
    list.innerHTML = sorted.map(brief => `
      <div class="archive-item">
        <span class="queue-item-date">${formatDisplayDate(brief.date)}</span>
        <span class="queue-item-preview">${stripHTML(brief.html).slice(0,120)}…</span>
        <div class="queue-item-actions">
          <span class="status-badge status-published">Published</span>
        </div>
      </div>
    `).join('');
  } catch (err) {
    list.innerHTML = `<div class="empty-state">Could not load archive: ${err.message}</div>`;
  }
}

// ── Settings ──────────────────────────────────────────────────────────
function loadSettings() {
  const s = getSettings();
  document.getElementById('autoPublishToggle').checked = s.autoPublish || false;
  document.getElementById('styleGuidance').value = s.styleGuidance || '';
  // Show current token status (masked)
  const token = getGitHubToken();
  const tokenField = document.getElementById('githubToken');
  if (tokenField) tokenField.placeholder = token ? '••••••••••••••••••••• (token saved)' : 'Paste your GitHub token here';
}
function saveSettings() {
  const s = {
    autoPublish: document.getElementById('autoPublishToggle').checked,
    styleGuidance: document.getElementById('styleGuidance').value
  };
  saveSettingsToStorage(s);
  // Save GitHub token if provided
  const tokenField = document.getElementById('githubToken');
  if (tokenField && tokenField.value.trim()) {
    localStorage.setItem(STORAGE_KEY_TOKEN, tokenField.value.trim());
    tokenField.value = '';
    tokenField.placeholder = '••••••••••••••••••••• (token saved)';
    showToast('✓ Settings and GitHub token saved.', '#1e8449');
  } else {
    showToast('✓ Settings saved.', '#1e8449');
  }
}

// ── Utils ─────────────────────────────────────────────────────────────
function stripHTML(html) {
  const div = document.createElement('div');
  div.innerHTML = html;
  return div.textContent || div.innerText || '';
}

// ── Init ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('gateHint').textContent = '';
});
