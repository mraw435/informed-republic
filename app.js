// ─── INFORMED REPUBLIC — app.js ────────────────────────────────────────

// ── GitHub config ─────────────────────────────────────────────────────
const GITHUB_BRIEFS_URL = 'https://raw.githubusercontent.com/mraw435/informed-republic/main/briefs.json';

// ── Date helpers ──────────────────────────────────────────────────────
function todayKey() {
  return new Date().toISOString().slice(0, 10);
}
function formatDisplayDate(isoDate) {
  const d = new Date(isoDate + 'T12:00:00');
  return d.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
}

// ── Render the brief on homepage ──────────────────────────────────────
async function renderHomepageBrief() {
  const loading = document.getElementById('briefLoading');
  const content = document.getElementById('briefContent');
  const pending = document.getElementById('briefPending');
  if (!loading) return;

  const key = todayKey();

  try {
    // Fetch briefs.json from GitHub (cache-busted so visitors always get latest)
    const res = await fetch(GITHUB_BRIEFS_URL + '?t=' + Date.now());
    if (!res.ok) throw new Error('Could not load briefs');
    const data = await res.json();
    const briefs = data.briefs || [];

    // Find today's brief
    const todayBrief = briefs.find(b => b.date === key);

    loading.style.display = 'none';

    if (todayBrief) {
      document.getElementById('briefDate').textContent = formatDisplayDate(key);
      document.getElementById('briefBody').innerHTML = todayBrief.html;
      content.style.display = 'block';
    } else {
      document.getElementById('briefPendingDate').textContent = formatDisplayDate(key);
      pending.style.display = 'block';
    }
  } catch (err) {
    // Fallback — show pending state if GitHub is unreachable
    loading.style.display = 'none';
    document.getElementById('briefPendingDate').textContent = formatDisplayDate(key);
    pending.style.display = 'block';
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
