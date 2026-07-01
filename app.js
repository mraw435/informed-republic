// ─── INFORMED REPUBLIC — app.js ────────────────────────────────────────

const STORAGE_KEY_BRIEFS = 'ir_briefs';

// ── Date helpers ──────────────────────────────────────────────────────
function todayKey() {
  return new Date().toISOString().slice(0, 10); // YYYY-MM-DD
}

function formatDisplayDate(isoDate) {
  const d = new Date(isoDate + 'T12:00:00');
  return d.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
}

// ── Load briefs from localStorage ────────────────────────────────────
function getBriefs() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY_BRIEFS) || '{}');
  } catch { return {}; }
}

// ── Render the brief on homepage ─────────────────────────────────────
function renderHomepageBrief() {
  const loading   = document.getElementById('briefLoading');
  const content   = document.getElementById('briefContent');
  const pending   = document.getElementById('briefPending');
  if (!loading) return;

  const briefs = getBriefs();
  const key    = todayKey();
  const brief  = briefs[key];

  loading.style.display = 'none';

  if (brief && brief.status === 'published') {
    // Show published brief
    document.getElementById('briefDate').textContent = formatDisplayDate(key);
    document.getElementById('briefBody').innerHTML = brief.html;
    content.style.display = 'block';
  } else if (brief && brief.status === 'pending') {
    // Show "under review" message
    document.getElementById('briefPendingDate').textContent = formatDisplayDate(key);
    pending.style.display = 'block';
  } else {
    // No brief yet for today
    pending.style.display = 'block';
    document.getElementById('briefPendingDate').textContent = formatDisplayDate(key);
  }
}

// ── Subscribe handler ─────────────────────────────────────────────────
function handleSubscribe(e) {
  e.preventDefault();
  showToast('✓ You\'re subscribed! Check your inbox.');
  e.target.reset();
}

function showToast(msg) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3500);
}

// ── Date in topbar ────────────────────────────────────────────────────
function setTopbarDate() {
  const el = document.getElementById('topbarDate');
  if (!el) return;
  el.textContent = new Date().toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric', year: 'numeric'
  });
}

// ── Footer year ───────────────────────────────────────────────────────
function setFooterYear() {
  const el = document.getElementById('footerYear');
  if (el) el.textContent = new Date().getFullYear();
}

// ── Init ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  setTopbarDate();
  setFooterYear();
  renderHomepageBrief();
});
