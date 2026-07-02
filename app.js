// ─── INFORMED REPUBLIC — app.js ────────────────────────────────────────

// ── GitHub config ─────────────────────────────────────────────────────
const GITHUB_BRIEFS_URL = 'https://raw.githubusercontent.com/mraw435/informed-republic/main/briefs.json';
const MEMBERS_URL = 'members.json';

// ── State ─────────────────────────────────────────────────────────────
let allMembers = [];

// ── Date helpers ──────────────────────────────────────────────────────
function todayKey() {
  return new Date().toISOString().slice(0, 10);
}
function formatDisplayDate(isoDate) {
  const d = new Date(isoDate + 'T12:00:00');
  return d.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
}

// ── Load members for name linking ─────────────────────────────────────
async function loadMembers() {
  try {
    const res = await fetch(MEMBERS_URL);
    if (!res.ok) return;
    const data = await res.json();
    allMembers = data.members || [];
  } catch { allMembers = []; }
}

// ── Auto-link member names in brief text ──────────────────────────────
function linkMemberNames(html) {
  if (!allMembers.length) return html;

  // Build name map: "First Last" -> member, sorted longest first to avoid partial matches
  const nameMap = [];
  allMembers.forEach(m => {
    // Full name variants to match
    const names = [
      `${m.first_name} ${m.last_name}`,
      m.last_name.length > 4 ? m.last_name : null, // only last name if >4 chars to avoid false matches
    ].filter(Boolean);

    names.forEach(name => {
      nameMap.push({ name, member: m });
    });
  });

  // Sort by length descending so "Mark Warner" matches before "Warner"
  nameMap.sort((a, b) => b.name.length - a.name.length);

  // Parse HTML safely using a temporary element
  const div = document.createElement('div');
  div.innerHTML = html;

  // Walk text nodes only (don't touch existing links/tags)
  const walker = document.createTreeWalker(div, NodeFilter.SHOW_TEXT, {
    acceptNode: node => {
      // Skip if inside an anchor tag already
      let parent = node.parentElement;
      while (parent) {
        if (parent.tagName === 'A') return NodeFilter.FILTER_REJECT;
        parent = parent.parentElement;
      }
      return NodeFilter.FILTER_ACCEPT;
    }
  });

  const nodesToReplace = [];
  while (walker.nextNode()) {
    nodesToReplace.push(walker.currentNode);
  }

  nodesToReplace.forEach(textNode => {
    let text = textNode.textContent;
    let matched = false;

    nameMap.forEach(({ name, member }) => {
      if (!text.includes(name)) return;
      matched = true;
      // Replace name with a linked version
      text = text.split(name).join(
        `<MEMBERLINK bioguide="${member.bioguide_id}" id="${member.id}">${name}</MEMBERLINK>`
      );
    });

    if (matched) {
      const span = document.createElement('span');
      span.innerHTML = text.replace(
        /<MEMBERLINK bioguide="([^"]+)" id="([^"]+)">([^<]+)<\/MEMBERLINK>/g,
        (_, bioguide, id, name) =>
          `<a href="#member-${bioguide}" class="member-link" onclick="openMemberFromBrief('${id}',event)">${name}</a>`
      );
      textNode.parentNode.replaceChild(span, textNode);
    }
  });

  return div.innerHTML;
}

// ── Member modal on homepage ──────────────────────────────────────────
function openMemberFromBrief(memberId, event) {
  event.preventDefault();
  const member = allMembers.find(m => m.id === memberId);
  if (!member) return;

  // Update URL for SEO/shareability
  history.pushState({ memberId }, '', `#member-${member.bioguide_id}`);

  populateMemberModal(member);
  document.getElementById('memberModalOverlay').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function populateMemberModal(member) {
  // Photo
  document.getElementById('mmPhoto').innerHTML = `
    <img src="https://unitedstates.github.io/images/congress/225x275/${member.bioguide_id}.jpg"
         alt="${member.display_name}"
         style="width:100%;height:100%;object-fit:cover"
         onerror="this.style.display='none';this.nextElementSibling.style.display='flex'" />
    <span class="modal-photo-placeholder" style="display:none">👤</span>`;

  document.getElementById('mmName').textContent = member.display_name;
  document.getElementById('mmSubtitle').textContent =
    `${member.state}${member.district ? `, District ${member.district}` : ''} · ${member.chamber}`;

  document.getElementById('mmChips').innerHTML =
    `<span class="modal-chip">${member.party}</span>
     <span class="modal-chip">${member.chamber}</span>`;

  document.getElementById('mmContact').innerHTML = `
    <span class="modal-contact-item">📞 ${member.phone || 'Not available'}</span>
    <span class="modal-contact-item">🚪 ${member.office_room || 'Not available'}</span>`;

  const bio = member.profile?.bio || '';
  document.getElementById('mmBio').textContent = bio || 'Biography coming soon.';

  const committees = member.profile?.committees || [];
  const commSection = document.getElementById('mmCommitteeSection');
  if (committees.length) {
    document.getElementById('mmCommittees').innerHTML =
      committees.map(c => `<div class="modal-committee">${c}</div>`).join('');
    commSection.style.display = 'block';
  } else {
    commSection.style.display = 'none';
  }

  const yrs = member.profile?.years_served;
  document.getElementById('mmYears').textContent = yrs
    ? `In office since ${yrs} · ${new Date().getFullYear() - yrs} years`
    : '';

  const officialLink = document.getElementById('mmOfficialLink');
  officialLink.href = member.official_url || '#';

  const fullProfileLink = document.getElementById('mmFullProfileLink');
  fullProfileLink.href = `officials.html#${member.id}`;
}

function closeMemberModal(e) {
  if (e && e.target !== document.getElementById('memberModalOverlay')) return;
  closeMemberModalDirect();
}
function closeMemberModalDirect() {
  document.getElementById('memberModalOverlay').classList.remove('open');
  document.body.style.overflow = '';
  history.pushState({}, '', window.location.pathname);
}

// Handle browser back button closing modal
window.addEventListener('popstate', () => {
  const overlay = document.getElementById('memberModalOverlay');
  if (overlay && overlay.classList.contains('open')) {
    overlay.classList.remove('open');
    document.body.style.overflow = '';
  }
});

// ── Render the brief on homepage ──────────────────────────────────────
async function renderHomepageBrief() {
  const loading = document.getElementById('briefLoading');
  const content = document.getElementById('briefContent');
  const pending = document.getElementById('briefPending');
  if (!loading) return;

  const key = todayKey();

  try {
    const res = await fetch(GITHUB_BRIEFS_URL + '?t=' + Date.now());
    if (!res.ok) throw new Error('Could not load briefs');
    const data = await res.json();
    const briefs = data.briefs || [];
    const todayBrief = briefs.find(b => b.date === key);

    loading.style.display = 'none';

    if (todayBrief) {
      document.getElementById('briefDate').textContent = formatDisplayDate(key);
      // Link member names after members are loaded
      const linkedHTML = linkMemberNames(todayBrief.html);
      document.getElementById('briefBody').innerHTML = linkedHTML;
      content.style.display = 'block';
    } else {
      document.getElementById('briefPendingDate').textContent = formatDisplayDate(key);
      pending.style.display = 'block';
    }
  } catch (err) {
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

// ── Escape key closes modal ───────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeMemberModalDirect();
});

// ── Init ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  setTopbarDate();
  setFooterYear();
  await loadMembers();      // load members first so linking works
  await renderHomepageBrief();
});
