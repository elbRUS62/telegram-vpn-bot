const tg = window.Telegram.WebApp;
 tg.ready();
 tg.expand();
 try { tg.setHeaderColor('secondary_bg_color'); } catch (_) {}
 try { tg.setBackgroundColor('bg_color'); } catch (_) {}
 try { tg.setBottomBarColor?.('bg_color'); } catch (_) {}

 let CURRENT_SUB_DATA = null;
 let CURRENT_SUB_URL = "";
 let INVITE_NO_TG_URL = "";
 let CACHED_DOCS = null;
 let POLLING_TIMER = null;
 let SUB_TIMER = null;
 let IS_ADMIN = false;
 let INIT_DATA = tg.initData || "";
 let SUPPORT_STATE = { view: 'list', ticket: null };
 let TICKETS_STATE = { filter: 'active', current: null, busy: false };


 async function apiCall(path, body = {}) {
 if (!INIT_DATA) {
 INIT_DATA = tg.initData || "";
 }
 const res = await fetch(path, {
 method: 'POST',
 headers: {'Content-Type': 'application/json'},
 body: JSON.stringify({init_data: INIT_DATA, ...body}),
 });
 if (res.status === 401) console.warn("Ошибка 401: init_data пустой или неверный");
 return res.json();
 }

 function updateDots(activeIndex = null) {
 try {
 const tabsContainer = document.getElementById('tabs');
 const dotsContainer = document.getElementById('tabs-dots');
 if (!tabsContainer || !dotsContainer) return;

 const tabs = tabsContainer.querySelectorAll('.tab');
 
 // Создаём точки, если их нет
 if (dotsContainer.children.length !== tabs.length) {
 dotsContainer.innerHTML = '';
 tabs.forEach(() => {
 const dot = document.createElement('div');
 dot.className = 'dot';
 dotsContainer.appendChild(dot);
 });
 }

 // Скрываем точки, если вкладки помещаются
 if (tabsContainer.scrollWidth <= tabsContainer.clientWidth) {
 dotsContainer.style.display = 'none';
 return;
 } else {
 dotsContainer.style.display = 'flex';
 }

 // Если индекс не передан — ищем активную вкладку
 if (activeIndex === null) {
 tabs.forEach((tab, index) => {
 if (tab.classList.contains('active')) activeIndex = index;
 });
 }

 // Подсвечиваем нужную точку
 dotsContainer.querySelectorAll('.dot').forEach((dot, index) => {
 dot.classList.toggle('active', index === activeIndex);
 });
 } catch (e) {
 console.warn('updateDots error:', e);
 }
 }

 // Слушатель скролла для вкладок

 // Инициализация индикатора после загрузки
 document.addEventListener('DOMContentLoaded', () => {
 const tabsEl = document.getElementById('tabs');
 if (tabsEl) tabsEl.addEventListener('scroll', updateDots);
 setTimeout(updateDots, 500);
 window.addEventListener('resize', updateDots);
 });

 // Прокрутка вкладок колёсиком
 const tabsElWheel = document.getElementById('tabs');
 if (tabsElWheel) {
 tabsElWheel.addEventListener('wheel', (e) => {
 if (e.deltaY !== 0) {
 e.preventDefault();
 tabsElWheel.scrollLeft += e.deltaY;
 }
 }, { passive: false });
 }

 function showToast(text, isError = false) {
 const toast = document.getElementById('toast');
 toast.textContent = text;
 const errorKeywords = ['максимальный срок', 'Сначала получите', 'Ошибка', 'Не удалось', 'Нет активной', 'Доступ запрещён', 'Неверная авторизация'];
 const looksLikeError = isError || errorKeywords.some(kw => text.includes(kw));
 if (looksLikeError) toast.classList.add('error');
 else toast.classList.remove('error');
 toast.classList.add('show');
 setTimeout(() => toast.classList.remove('show'), 3500);
 }

 function copyToClipboard(text) {
 navigator.clipboard.writeText(text).then(() => showToast('Скопировано!')).catch(() => showToast('Не удалось скопировать'));
 }

 function shareSubscription(url, text = 'Подписка SkrepNet') {
   const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`;
   if (tg.openTelegramLink) tg.openTelegramLink(shareUrl);
   else window.open(shareUrl, '_blank');
 }

 function openInviteNoTgModal(url, qrBase64 = '') {
   INVITE_NO_TG_URL = url || "";
   const link = document.getElementById('invite-no-tg-link');
   if (link) link.textContent = INVITE_NO_TG_URL || '—';
   const qrWrap = document.getElementById('invite-no-tg-qr-wrap');
   const qrImg = document.getElementById('invite-no-tg-qr');
   if (qrWrap && qrImg) {
     if (qrBase64) {
       qrImg.src = 'data:image/png;base64,' + qrBase64;
       qrWrap.style.display = 'block';
     } else {
       qrImg.removeAttribute('src');
       qrWrap.style.display = 'none';
     }
   }
   document.getElementById('invite-no-tg-modal').classList.add('show');
 }

 async function shareInviteNoTgLink() {
   if (!INVITE_NO_TG_URL) return;
   const text = 'VPN для друга — SkrepNet';
   if (navigator.share) {
     try {
       await navigator.share({ title: 'SkrepNet', text, url: INVITE_NO_TG_URL });
       return;
     } catch (e) {
       if (e && e.name === 'AbortError') return;
     }
   }
   copyToClipboard(INVITE_NO_TG_URL);
 }

 // Кастомное окно подтверждения (нативное, в стиле Telegram)
 function showConfirm(text, title = 'Подтверждение') {
 return new Promise((resolve) => {
 const modal = document.getElementById('confirm-modal');
 document.getElementById('confirm-title').textContent = title;
 document.getElementById('confirm-text').textContent = text;
 modal.classList.add('show');
 
 const okBtn = document.getElementById('confirm-ok');
 const cancelBtn = document.getElementById('confirm-cancel');
 
 const cleanup = () => {
 modal.classList.remove('show');
 okBtn.removeEventListener('click', onOk);
 cancelBtn.removeEventListener('click', onCancel);
 };
 
 const onOk = () => { cleanup(); resolve(true); };
 const onCancel = () => { cleanup(); resolve(false); };
 
 okBtn.addEventListener('click', onOk);
 cancelBtn.addEventListener('click', onCancel);
 });
 }

 
// ==================== Slide-to-submit ====================
function initSlideToSub() {
  document.querySelectorAll('.slide-to-sub').forEach((slider) => {
    if (slider.dataset.slideInit) return; // уже инициализирован
    slider.dataset.slideInit = '1';

    const thumb = slider.querySelector('.slide-to-sub__thumb');
    if (!thumb) return;

    let startX = 0;
    let currentX = 0;
    let maxX = 0;
    let dragging = false;

    const getMaxX = () => slider.clientWidth - thumb.offsetWidth - 8; // 4px слева + 4px справа

    const onDown = (e) => {
      e.preventDefault();
      e.stopPropagation();
      dragging = true;
      maxX = getMaxX();
      startX = (e.touches ? e.touches[0].clientX : e.clientX) - currentX;
      slider.classList.add('is-dragging');
      slider.setPointerCapture?.(e.pointerId);
    };

    const onMove = (e) => {
      if (!dragging) return;
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      let x = clientX - startX;
      if (x < 0) x = 0;
      if (x > maxX) x = maxX;
      currentX = x;
      thumb.style.transform = `translateX(${x}px)`;
      e.preventDefault();
    };

    const onUp = () => {
      if (!dragging) return;
      dragging = false;
      slider.classList.remove('is-dragging');
      const threshold = maxX * 0.85;
      if (currentX >= threshold) {
        // успех
        slider.classList.add('is-done');
        thumb.style.transform = `translateX(${maxX}px)`;
        try { tg?.HapticFeedback?.impactOccurred?.('medium'); } catch (_) {}
        setTimeout(() => {
          openTermsModal();
          // сброс через 400мс, чтобы не мигало при возврате
          setTimeout(() => {
            slider.classList.remove('is-done');
            currentX = 0;
            thumb.style.transform = 'translateX(0)';
          }, 400);
        }, 200);
      } else {
        // откат
        currentX = 0;
        thumb.style.transform = 'translateX(0)';
      }
    };

    thumb.addEventListener('pointerdown', onDown);
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
  });
}

// Вызываем после каждого рендера главного экрана и при загрузке
document.addEventListener('DOMContentLoaded', initSlideToSub);
// Патч рендера: после loadMain(), но проще — MutationObserver на #main-content
const _slideObserver = new MutationObserver(() => initSlideToSub());
document.addEventListener('DOMContentLoaded', () => {
  const mainContent = document.getElementById('main-content');
  if (mainContent) _slideObserver.observe(mainContent, { childList: true, subtree: true });
});

document.querySelectorAll('.tab').forEach((tab, index) => {
 tab.addEventListener('click', () => {
 const name = tab.dataset.tab;
 document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
 document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
 tab.classList.add('active');
 document.getElementById('screen-' + name).classList.add('active');
 updateDots(index);

 setTimeout(updateDots, 100);
 if (name === 'main') loadMain();
 else if (name === 'sub') {
 if (SUB_TIMER) { clearInterval(SUB_TIMER); SUB_TIMER = null; }
 loadSubscription();
 SUB_TIMER = setInterval(() => {
 if (document.getElementById('screen-sub').classList.contains('active')) loadSubscription(true);
 else { clearInterval(SUB_TIMER); SUB_TIMER = null; }
 }, 5000);
 }
 else if (name === 'donate') loadDonate();
 else if (name === 'support') loadSupport();
 else if (name === 'admin') loadAdmin();
 });
 });

 function switchTab(name) {
 const tab = document.querySelector(`.tab[data-tab="${name}"]`);
 if (tab) tab.click();
 }

 function updateAdminTabBadge(count) {
 const badge = document.getElementById('tab-admin-badge');
 if (!badge) return;
 if (count > 0) { badge.textContent = count; badge.style.display = 'inline-block'; }
 else badge.style.display = 'none';
 }

 function updateSupportTabBadge(count) {
 const badge = document.getElementById('tab-support-badge');
 if (!badge) return;
 if (count > 0) { badge.textContent = count; badge.style.display = 'inline-block'; }
 else badge.style.display = 'none';
 }

 // ==================== ГЛАВНОЕ МЕНЮ ====================
 async function loadMain(isSilent = false) {
 const loading = document.getElementById('main-loading');
 const content = document.getElementById('main-content');
 
 if (!isSilent) { loading.style.display = 'block'; content.style.display = 'none'; }
 if (POLLING_TIMER) { clearTimeout(POLLING_TIMER); POLLING_TIMER = null; }

 try {
 const data = await apiCall('/api/miniapp/main');
 
 if (isSilent) {
 const currentStatusEl = content.querySelector('.status-badge');
 const currentStatusText = currentStatusEl ? currentStatusEl.textContent : '';
 if (currentStatusText === data.status_text) {
 if (data.status === 'pending') POLLING_TIMER = setTimeout(() => loadMain(true), 5000);
 return;
 }
 }

 loading.style.display = 'none';
 content.style.display = 'block';

 if (data.error) {
 if (!isSilent) content.innerHTML = `<div class="error"> ${data.error}</div>`;
 return;
 }

 if (data.status === 'pending') POLLING_TIMER = setTimeout(() => loadMain(true), 5000);

 CURRENT_SUB_URL = data.sub_url || '';
 const statusClass = data.status === 'active' ? 'active' : (data.status === 'pending' ? 'pending' : (data.status === 'rejected' ? 'expired' : 'new'));
 const isActive = !!data.has_subscription;
 const isPending = data.status === 'pending';
 const isRejected = data.status === 'rejected';

 const heroTitle = isPending ? 'Заявка отправлена' : 'Твой интернет';
 const heroText = isActive
   ? 'Подписка активна. Трафик не ограничен.'
   : (isPending
     ? 'Проверяем заявку. Обычно это занимает немного времени.'
     : (isRejected
       ? 'Заявка отклонена. Можно попробовать снова или написать в поддержку.'
       : 'Бесплатный доступ для всех. Трафик без ограничений.'));

 let primaryAction = '';
 if (isActive) {
   primaryAction = `<button class="btn btn-primary" data-action="switch_sub">Открыть подписку</button>`;
 } else if (isPending) {
   primaryAction = `<button class="btn btn-primary" disabled>Заявка на рассмотрении</button>`;
 } else {
   primaryAction = `<button class="btn btn-primary" data-action="get_sub">${isRejected ? 'Подать заявку снова' : 'Получить подписку'}</button>`;
 }

 const quickActions = [
   isActive ? { action: 'invite_friend', label: 'Пригласить друга', meta: '' } : null,
   isActive ? { action: 'invite_no_tg', label: 'Добавить без Telegram', meta: '' } : null,
   { action: 'connect_help', label: 'Как подключиться', meta: 'Инструкция' },
   { action: 'donate', label: '❤️ Поддержать проект', meta: 'По желанию' },
 ].filter(Boolean);

 const quickHtml = quickActions.map(item => `
   <button class="tg-item" data-action="${item.action}">
     <span>${item.label}</span>
     <span class="${item.meta ? 'tg-item__meta' : 'tg-item__arrow'}">${item.meta || '›'}</span>
   </button>
 `).join('');

 content.innerHTML = `
 <div class="tg-hero tg-card">
   <div class="tg-kicker">${data.bot_name || 'SkrepNet'}</div>
   <h1 class="tg-title">${heroTitle}</h1>
   <p class="tg-subtitle">${heroText}</p>
   <div class="tg-chips">
     <span class="status-badge ${statusClass}">${data.status_text}</span>
     <span class="tg-chip">Бесплатно</span>
     <span class="tg-chip tg-chip--muted">Без лимитов</span>
   </div>
 </div>

 <div class="tg-card" style="padding:12px;">
   ${primaryAction}
 </div>

 <div class="tg-list">
   ${quickHtml}
 </div>

 <div style="text-align:center;margin-top:4px;font-size:13px;">
   <a href="#" id="docs-link" class="tg-link">Пользовательские соглашения</a>
 </div>
 `;

 content.querySelectorAll('[data-action]').forEach(btn => {
 btn.addEventListener('click', async () => {
 const action = btn.dataset.action;
 if (action === 'switch_sub') switchTab('sub');
 else if (action === 'donate') switchTab('donate');
 else if (action === 'get_sub') openTermsModal();
 else if (action === 'invite_friend') {
 if (!data.has_subscription) { showToast('Сначала получите подписку'); return; }
 openRefModal();
 }
 else if (action === 'invite_no_tg') {
 if (!data.has_subscription) { showToast('Сначала получите подписку'); return; }
 if (btn.disabled) return;
 btn.disabled = true;
 try {
   const r = await apiCall('/api/miniapp/create_invite_link', { friend_input: '' });
   if (r.error) { showToast(r.error, true); return; }
   if (!r.invite_url) throw new Error('Не удалось создать ссылку');
   openInviteNoTgModal(r.invite_url, r.qr_base64);
 } catch (e) {
   showToast(e.message || 'Не удалось создать приглашение', true);
 } finally {
   btn.disabled = false;
 }
 }
 else if (action === 'connect_help') openConnectModal();
 });
 });

 const docsLink = document.getElementById('docs-link');
 if (docsLink) {
 docsLink.addEventListener('click', (e) => { e.preventDefault(); openDocsModal(); });
 }

 IS_ADMIN = !!data.is_admin;
 const tabAdmin = document.getElementById('tab-admin');
 if (tabAdmin) tabAdmin.style.display = IS_ADMIN ? '' : 'none';
 updateSupportTabBadge(data.support_unread || 0);
 
 if (IS_ADMIN) {
 adminCall('/stats').then(r => {
 if (r && !r.error) updateAdminTabBadge((r.pending || 0) + (r.tickets_unread || 0));
 });
 }

 } catch (e) {
 loading.style.display = 'none';
 content.style.display = 'block';
 if (!isSilent) content.innerHTML = `<div class="error"> ${e.message}</div>`;
 }
 }

 // ==================== МОЯ ПОДПИСКА ====================
 async function loadSubscription(isSilent = false) {
 const loading = document.getElementById('sub-loading');
 const content = document.getElementById('sub-content');

 if (!isSilent) { loading.style.display = 'block'; content.style.display = 'none'; }

 try {
 const data = await apiCall('/api/miniapp/subscription');

 if (isSilent && CURRENT_SUB_DATA) {
 const changed = 
 data.traffic_down !== CURRENT_SUB_DATA.traffic_down ||
 data.traffic_up !== CURRENT_SUB_DATA.traffic_up ||
 data.days_left !== CURRENT_SUB_DATA.days_left ||
 data.status !== CURRENT_SUB_DATA.status ||
 data.is_online !== CURRENT_SUB_DATA.is_online ||
 data.expires_at !== CURRENT_SUB_DATA.expires_at;
 if (!changed) return;
 }

 loading.style.display = 'none';
 content.style.display = 'block';

 if (data.error) {
 content.innerHTML = `
 <div class="tg-hero">
   <div class="tg-kicker">Моя подписка</div>
   <h1 class="tg-title">Подписка не активна</h1>
   <p class="tg-subtitle">Получи бесплатный доступ на главной странице.</p>
 </div>
 <div class="tg-card">
   <button class="btn btn-primary" onclick="switchTab('main')">Перейти на главную</button>
 </div>
 `;
 return;
 }

 CURRENT_SUB_DATA = data;
 CURRENT_SUB_URL = data.sub_url || CURRENT_SUB_URL;
 const daysLeft = data.days_left || 0;
 const totalDays = 30;
 const isUnlimited = data.expires_at === '∞';
 const daysPercent = isUnlimited ? 100 : Math.min(100, Math.max(0, (daysLeft / totalDays) * 100));
 const daysLabel = isUnlimited ? 'Бессрочно' : `${daysLeft} дн.`;
 const progressColor = isUnlimited ? 'var(--button-color)' : getProgressColor(daysLeft, totalDays);

 content.innerHTML = `
 <div class="tg-hero">
   <div class="tg-kicker">Моя подписка</div>
   <h1 class="tg-title">${data.status_text}</h1>
   <p class="tg-subtitle">${data.first_name || 'Пользователь'}${data.username ? ' · @' + data.username : ''}</p>
 </div>

 <div class="tg-list">
   <div class="tg-item tg-item--static">
     <span class="tg-item__label">Доступ</span>
     <span class="tg-item__value tg-item__value--accent">Бесплатно</span>
   </div>
   <div class="tg-item tg-item--static">
     <span class="tg-item__label">Трафик</span>
     <span class="tg-item__value tg-item__value--accent">Без ограничений</span>
   </div>
   <div class="tg-item tg-item--static">
     <span class="tg-item__label">Действует до</span>
     <span class="tg-item__value">${data.expires_at}</span>
   </div>
   <div class="tg-item tg-item--static">
     <span class="tg-item__label">Осталось</span>
     <span class="tg-item__value">${daysLabel}</span>
   </div>
 </div>

 <div class="tg-card">
   <div class="tg-card-title">Срок подписки</div>
   <div class="tg-progress"><span style="width:${daysPercent}%;background:${progressColor};"></span></div>
   <div class="tg-note" style="margin-top:8px;padding:0;">${isUnlimited ? 'Срок не ограничен' : 'Продление бесплатное'}</div>
 </div>

 <div class="tg-list">
   <div class="tg-item tg-item--static">
     <span class="tg-item__label">Скачано</span>
     <span class="tg-item__value">${data.traffic_down}</span>
   </div>
   <div class="tg-item tg-item--static">
     <span class="tg-item__label">Загружено</span>
     <span class="tg-item__value">${data.traffic_up}</span>
   </div>
   <div class="tg-item tg-item--static">
     <span class="tg-item__label">Подключение</span>
     <span class="tg-status ${data.is_online ? 'tg-status--online' : ''}">${data.is_online ? 'Онлайн' : 'Оффлайн'}</span>
   </div>
 </div>

 <div class="tg-card">
   <div class="tg-card-title">Подключение</div>
   <p class="tg-note" style="margin-bottom:0;padding:0;">Отсканируй QR-код в Happ или скопируй ссылку.</p>
   <div class="qr-wrap">
     <img src="data:image/png;base64,${data.qr_base64}" alt="QR-код подписки">
   </div>
   <button class="btn btn-primary" data-action="copy_link">Скопировать ссылку</button>
   <button class="btn btn-secondary" data-action="share_link">Поделиться ссылкой</button>
   <a href="data:image/png;base64,${data.qr_base64}" download="skrepnet-qr.png" class="btn btn-secondary" style="text-decoration:none;">Сохранить QR</a>
 </div>

 <div class="tg-card">
   <button class="btn btn-secondary" data-action="renew_sub">Продлить бесплатно</button>
   <button class="btn btn-secondary" data-action="donate">❤️ Поддержать проект</button>
 </div>

 <div class="tg-note" style="text-align:center;">Трафик не ограничен. Платные тарифы не используются.</div>

 <div style="text-align:center; margin-top:4px;">
   <button class="tg-link" style="background:none;border:0;font:inherit;font-size:13px;cursor:pointer;" onclick="switchTab('support')">Проблема с подключением? Перейти в помощь</button>
 </div>
 `;

 content.querySelectorAll('[data-action]').forEach(btn => {
 btn.addEventListener('click', () => {
 if (btn.dataset.action === 'copy_link') {
   copyToClipboard(data.sub_url);
 }
 else if (btn.dataset.action === 'share_link') shareSubscription(data.sub_url);
 else if (btn.dataset.action === 'renew_sub') openRenewModal();
 else if (btn.dataset.action === 'donate') switchTab('donate');
 });
 });

 } catch (e) {
 loading.style.display = 'none';
 content.style.display = 'block';
 if (!isSilent) content.innerHTML = `<div class="error"> ${e.message}</div>`;
 }
 }

 function getProgressColor(daysLeft, totalDays) {
 const days = Math.max(0, Math.min(daysLeft, totalDays));
 const percent = days / totalDays;
 let r, g, b;
 if (percent > 0.5) {
 const t = (percent - 0.5) / 0.5;
 r = Math.round(210 + (0 - 210) * t);
 g = Math.round(153 + (200 - 153) * t);
 b = Math.round(34 + (80 - 34) * t);
 } else {
 const t = percent / 0.5;
 r = Math.round(248 + (210 - 248) * t);
 g = Math.round(81 + (153 - 81) * t);
 b = Math.round(73 + (34 - 73) * t);
 }
 return `rgb(${r}, ${g}, ${b})`;
 }

 function openRenewModal() {
 if (!CURRENT_SUB_DATA) return;
 document.getElementById('renew-current').textContent = CURRENT_SUB_DATA.expires_at;
 const parts = CURRENT_SUB_DATA.expires_at.split('.');
 if (parts.length === 3) {
 const cur = new Date(parts[2], parts[1] - 1, parseInt(parts[0]));
 const next = new Date(cur.getTime() + 30 * 24 * 60 * 60 * 1000);
 const newDate = String(next.getDate()).padStart(2, '0') + '.' + String(next.getMonth() + 1).padStart(2, '0') + '.' + next.getFullYear();
 document.getElementById('renew-new').textContent = newDate;
 }
 document.getElementById('renew-modal').classList.add('show');
 }

 document.getElementById('renew-cancel').addEventListener('click', () => document.getElementById('renew-modal').classList.remove('show'));
 document.getElementById('renew-confirm').addEventListener('click', async () => {
 const btn = document.getElementById('renew-confirm');
 btn.disabled = true; btn.textContent = 'Продлеваем...';
 try {
 const data = await apiCall('/api/miniapp/renew');
 if (data.error) { showToast(data.error); btn.disabled = false; btn.textContent = 'Продлить'; return; }
 showToast('Продлено до ' + data.new_expires_at);
 document.getElementById('renew-modal').classList.remove('show');
 btn.disabled = false; btn.textContent = 'Продлить';
 loadSubscription();
 } catch (e) {
 showToast(e.message); btn.disabled = false; btn.textContent = 'Продлить';
 }
 });

 // ==================== ДОНАТ ====================
 async function loadDonate() {
 const loading = document.getElementById('donate-loading');
 const content = document.getElementById('donate-content');
 loading.style.display = 'block'; content.style.display = 'none';
 try {
 const data = await apiCall('/api/miniapp/donate');
 loading.style.display = 'none'; content.style.display = 'block';
 if (data.error) { content.innerHTML = `<div class="error"> ${data.error}</div>`; return; }
 content.innerHTML = `
 <div class="tg-hero">
   <div class="tg-kicker">Поддержка проекта</div>
   <h1 class="tg-title">Помочь серверу</h1>
   <p class="tg-subtitle">Донат добровольный. Подписка остаётся бесплатной.</p>
 </div>

 <div class="tg-card">
   <div style="white-space:pre-line;line-height:1.5;">${data.donate_text}</div>
 </div>

 <div class="tg-card">
   <div class="tg-card-title">Сбор в ${data.next_month}</div>
   <div class="donate-progress"><span style="width:${data.progress_percent}%"></span></div>
   <div class="donate-progress-label">
     <strong>${data.progress_percent}%</strong>
     <span>${data.server_cost ? `${data.donated} ₽ из ${data.server_cost} ₽` : 'Сбор на сервер'}</span>
   </div>
 </div>

 <div class="tg-card">
   <button class="btn btn-secondary" data-action="stars">Поддержать звёздами</button>
   <a href="${data.donate_url}" target="_blank" style="display:block;text-decoration:none;"><button class="btn btn-primary" style="width:100%;margin-bottom:0;">Поддержать через DonationAlerts</button></a>
 </div>

 <div class="tg-note" style="text-align:center;">Донат не влияет на доступ и не открывает платных функций.</div>
 `;
 content.querySelectorAll('[data-action]').forEach(btn => {
 btn.addEventListener('click', async () => {
 if (btn.dataset.action === 'stars') {
 document.getElementById('stars-modal').classList.add('show');
 }
 });
 });
 } catch (e) {
 loading.style.display = 'none'; content.style.display = 'block';
 content.innerHTML = `<div class="error"> ${e.message}</div>`;
 }
 }

 // ==================== ПОДДЕРЖКА ====================
 function supportStatusBadge(status) {
 const cls = ['open', 'answered', 'closed'].includes(status) ? status : 'closed';
 const labels = { open: 'Открыт', answered: 'Есть ответ', closed: 'Закрыт' };
 return `<span class="ticket-status ${cls}">${labels[cls]}</span>`;
 }

 function supportTicketRow(t) {
 const unread = t.unread_user
 ? ' <span class="badge pending" style="margin-left:4px;">ответ</span>'
 : '';
 return `
 <div class="ticket-row" onclick="openSupportTicket(${t.id})">
  <div class="ticket-row__top">
   <span>${escapeHtml(t.subject)}${unread}</span>
   <span class="ticket-row__arrow">›</span>
  </div>
  <div class="ticket-row__meta">#${t.id} · ${escapeHtml(t.category_label || 'Другое')} · ${formatAuditTime(t.updated_at)}</div>
  <div class="ticket-row__last">${escapeHtml(t.last_text || '')}</div>
  <div style="margin-top:6px;">${supportStatusBadge(t.status)}</div>
 </div>`;
 }

 function renderSupportList(data) {
 const content = document.getElementById('support-content');
 const tickets = data.tickets || [];
 const username = data.support_username || 'SkrepNet_support';
 content.innerHTML = `
 <div class="header"><h1>Помощь</h1></div>
 <div class="card" style="padding:16px;">
  <p style="margin-bottom:12px;color:var(--hint-color);font-size:14px;line-height:1.5;">Опиши проблему — ответ придёт прямо в этот раздел и в Telegram.</p>
  <button class="btn btn-primary" style="width:100%;" onclick="openSupportNew()">Новое обращение</button>
 </div>
 <div class="card" style="padding:6px 16px 4px;">
  <div style="font-size:12px;color:var(--hint-color);padding:8px 0 2px;text-transform:uppercase;letter-spacing:.4px;">Мои обращения</div>
  ${tickets.length ? tickets.map(supportTicketRow).join('') : '<div class="ticket-empty">Обращений пока нет.<br>Если что-то не работает — создай первое.</div>'}
 </div>
 <div class="card" style="text-align:center;padding:14px;color:var(--hint-color);font-size:12px;line-height:1.6;">
  Срочный вопрос? <a href="https://t.me/${escapeHtml(username)}" target="_blank" style="color:var(--link-color);text-decoration:none;">@${escapeHtml(username)}</a>
 </div>`;
 }

 async function loadSupport() {
 const loading = document.getElementById('support-loading');
 const content = document.getElementById('support-content');
 loading.style.display = 'block'; content.style.display = 'none';
 SUPPORT_STATE = { view: 'list', ticket: null };
 try {
  const data = await apiCall('/api/miniapp/support/list');
  loading.style.display = 'none'; content.style.display = 'block';
  if (data.error) {
   content.innerHTML = `<div class="error"> ${escapeHtml(data.error)}</div>`;
   return;
  }
  updateSupportTabBadge(data.unread_count || 0);
  renderSupportList(data);
 } catch (e) {
  loading.style.display = 'none'; content.style.display = 'block';
  content.innerHTML = `<div class="error"> ${escapeHtml(e.message)}</div>`;
 }
 }

 function openSupportNew() {
 SUPPORT_STATE = { view: 'new', ticket: null };
 const content = document.getElementById('support-content');
 content.innerHTML = `
 <div class="header"><h1>Новое обращение</h1></div>
 <div class="card">
  <button class="ticket-back" onclick="loadSupport()">← Все обращения</button>
  <div class="ticket-form">
   <input id="support-subject" class="ticket-input" maxlength="120" placeholder="Тема (например: не подключается VPN)">
   <select id="support-category" class="ticket-select">
    <option value="connect">Подключение</option>
    <option value="payment">Оплата</option>
    <option value="account">Аккаунт</option>
    <option value="other">Другое</option>
   </select>
   <textarea id="support-message" class="ticket-textarea" maxlength="3000" placeholder="Опиши, что произошло. Чем больше деталей — тем быстрее поможем."></textarea>
   <div class="ticket-actions">
    <button class="btn btn-secondary" onclick="loadSupport()">Отмена</button>
    <button class="btn btn-primary" id="support-create-btn" onclick="submitSupportNew()">Отправить</button>
   </div>
  </div>
 </div>`;
 }

 async function submitSupportNew() {
 const subjectEl = document.getElementById('support-subject');
 const categoryEl = document.getElementById('support-category');
 const messageEl = document.getElementById('support-message');
 const btn = document.getElementById('support-create-btn');
 const subject = (subjectEl.value || '').trim();
 const message = (messageEl.value || '').trim();
 if (subject.length < 3) { showToast('Укажи тему обращения', true); subjectEl.focus(); return; }
 if (message.length < 3) { showToast('Опиши проблему подробнее', true); messageEl.focus(); return; }
 btn.disabled = true; btn.textContent = 'Отправляем...';
 const r = await apiCall('/api/miniapp/support/create', {
  subject, category: categoryEl.value, message
 });
 btn.disabled = false; btn.textContent = 'Отправить';
 if (r.error) { showToast(r.error, true); return; }
 showToast('Обращение отправлено');
 await openSupportTicket(r.ticket_id);
 }

 async function openSupportTicket(id) {
 const content = document.getElementById('support-content');
 const loading = document.getElementById('support-loading');
 loading.style.display = 'block'; content.style.display = 'none';
 try {
  const data = await apiCall('/api/miniapp/support/ticket', { ticket_id: id });
  loading.style.display = 'none'; content.style.display = 'block';
  if (data.error) { showToast(data.error, true); loadSupport(); return; }
  SUPPORT_STATE = { view: 'ticket', ticket: data.ticket };
  updateSupportTabBadge(0);
  renderSupportTicket(data);
 } catch (e) {
  loading.style.display = 'none'; content.style.display = 'block';
  content.innerHTML = `<div class="error"> ${escapeHtml(e.message)}</div>`;
 }
 }

 function renderSupportTicket(data) {
 const content = document.getElementById('support-content');
 const t = data.ticket;
 const messages = data.messages || [];
 const msgsHtml = messages.length
  ? messages.map(m => `
   <div class="ticket-msg ${m.sender === 'admin' ? 'admin' : 'user'}">
    <div class="ticket-msg__meta">${m.sender === 'admin' ? 'Поддержка' : 'Ты'} · ${formatAuditTime(m.created_at)}</div>
    ${escapeHtml(m.text)}
   </div>`).join('')
  : '<div class="ticket-empty">Сообщений пока нет.</div>';
 const replyHtml = t.status === 'closed'
  ? `<div class="ticket-subtle" style="margin-top:8px;">Обращение закрыто. Если проблема осталась — создай новое.</div>
     <button class="btn btn-secondary" style="margin-top:10px;" onclick="openSupportNew()">Новое обращение</button>`
  : `<div class="ticket-form">
      <textarea id="support-reply-text" class="ticket-textarea" maxlength="3000" placeholder="Написать сообщение..."></textarea>
      <div class="ticket-actions">
       <button class="btn btn-primary" id="support-reply-btn" onclick="sendSupportReply()">Отправить</button>
       <button class="btn btn-secondary" onclick="closeSupportTicket()">Закрыть</button>
      </div>
     </div>`;

 content.innerHTML = `
 <div class="header">
  <h1>Обращение #${t.id}</h1>
  <div style="margin-top:4px;">${supportStatusBadge(t.status)}</div>
 </div>
 <div class="card">
  <button class="ticket-back" onclick="loadSupport()">← Все обращения</button>
  <div style="font-size:16px;font-weight:600;margin-bottom:4px;">${escapeHtml(t.subject)}</div>
  <div class="ticket-subtle">${escapeHtml(t.category_label || 'Другое')} · ${formatAuditTime(t.created_at)}</div>
  <div class="ticket-divider"></div>
  <div class="ticket-msgs">${msgsHtml}</div>
  ${replyHtml}
 </div>`;
 }

 async function sendSupportReply() {
 const el = document.getElementById('support-reply-text');
 const btn = document.getElementById('support-reply-btn');
 const text = (el.value || '').trim();
 if (text.length < 2) { showToast('Сообщение слишком короткое', true); el.focus(); return; }
 if (!SUPPORT_STATE.ticket) return;
 btn.disabled = true; btn.textContent = 'Отправляем...';
 const r = await apiCall('/api/miniapp/support/reply', {
  ticket_id: SUPPORT_STATE.ticket.id, message: text
 });
 btn.disabled = false; btn.textContent = 'Отправить';
 if (r.error) { showToast(r.error, true); return; }
 await openSupportTicket(SUPPORT_STATE.ticket.id);
 }

 async function closeSupportTicket() {
 if (!SUPPORT_STATE.ticket) return;
 const ok = await showConfirm('Закрыть это обращение?', 'Закрыть обращение');
 if (!ok) return;
 const r = await apiCall('/api/miniapp/support/close', {
  ticket_id: SUPPORT_STATE.ticket.id
 });
 if (r.error) { showToast(r.error, true); return; }
 showToast('Обращение закрыто');
 loadSupport();
 }

 // ==================== ДОКУМЕНТЫ / РЕФЕРАЛКА / ТЕРМС ====================
 async function openDocsModal(startIndex = null, fromTerms = false) {
 const title = document.getElementById('docs-title');
 const content = document.getElementById('docs-content');
 title.textContent = "Пользовательские соглашения";
 content.innerHTML = "<div class='loading'> Загрузка...</div>";
 document.getElementById('docs-modal').classList.add('show');
 try {
 if (!CACHED_DOCS) {
 const data = await apiCall('/api/miniapp/profile');
 if (data.error) throw new Error(data.error);
 CACHED_DOCS = data.documents;
 }
 if (startIndex !== null) {
 const doc = CACHED_DOCS[startIndex];
 title.textContent = doc.title;
 content.innerHTML = `<div class="doc-text">${doc.content}</div><button class="btn btn-secondary" id="docs-back" style="margin-top: 16px;">Назад</button>`;
 document.getElementById('docs-back').addEventListener('click', () => {
 if (fromTerms) { document.getElementById('docs-modal').classList.remove('show'); document.getElementById('terms-modal').classList.add('show'); }
 else openDocsModal(null, false);
 });
 } else {
 const linksHtml = CACHED_DOCS.map((d, i) => `<button class="btn btn-secondary doc-btn" data-index="${i}" style="margin-bottom: 8px; text-align: left; padding-left: 16px;">${d.title}</button>`).join('');
 content.innerHTML = `<p style="margin-bottom:16px;color:var(--hint-color);font-size:14px;">Выберите документ:</p>${linksHtml}`;
 content.querySelectorAll('.doc-btn').forEach(btn => btn.addEventListener('click', () => openDocsModal(parseInt(btn.dataset.index), fromTerms)));
 }
 } catch (e) { content.innerHTML = `<div class="error"> Ошибка: ${e.message}</div>`; }
 }

 document.getElementById('docs-close').addEventListener('click', () => document.getElementById('docs-modal').classList.remove('show'));

 async function openRefModal() {
 const linkEl = document.getElementById('ref-link');
 const countEl = document.getElementById('ref-count');
 linkEl.textContent = 'Загрузка...'; countEl.textContent = '0';
 document.getElementById('ref-modal').classList.add('show');
 try {
 const data = await apiCall('/api/miniapp/referral');
 if (data.error) throw new Error(data.error);
 linkEl.textContent = data.ref_link; countEl.textContent = data.invites_count;
 document.getElementById('ref-copy-btn').onclick = () => copyToClipboard(data.ref_link);
 } catch (e) { linkEl.textContent = 'Ошибка: ' + e.message; }
 }
 document.getElementById('ref-close-btn').addEventListener('click', () => document.getElementById('ref-modal').classList.remove('show'));
 document.getElementById('invite-no-tg-copy').addEventListener('click', () => copyToClipboard(INVITE_NO_TG_URL));
 document.getElementById('invite-no-tg-share').addEventListener('click', shareInviteNoTgLink);
 document.getElementById('invite-no-tg-close').addEventListener('click', () => document.getElementById('invite-no-tg-modal').classList.remove('show'));

 function detectPlatformKey() {
   const platform = String(tg.platform || '').toLowerCase();
   const ua = String(navigator.userAgent || '').toLowerCase();
   if (platform === 'android' || platform === 'android_x') return 'android';
   if (platform === 'ios') return 'ios';
   if (platform === 'macos') return 'macos';
   if (platform === 'windows') return 'windows';
   if (platform === 'linux') return 'linux';
   if (platform === 'tdesktop') {
     if (ua.includes('mac')) return 'macos';
     if (ua.includes('win')) return 'windows';
     if (ua.includes('linux')) return 'linux';
   }
   if (ua.includes('android')) return 'android';
   if (ua.includes('iphone') || ua.includes('ipad')) return 'ios';
   if (ua.includes('mac os')) return 'macos';
   if (ua.includes('windows')) return 'windows';
   if (ua.includes('linux')) return 'linux';
   return null;
 }

 async function openConnectModal() {
 const title = document.getElementById('connect-title');
 const content = document.getElementById('connect-content');
 title.textContent = "Как подключиться";
 content.innerHTML = "<div class='loading'>Загрузка...</div>";
 document.getElementById('connect-modal').classList.add('show');
 try {
 const data = await apiCall('/api/miniapp/connect');
 if (data.error) throw new Error(data.error);

 const detected = detectPlatformKey();
 const platforms = data.platforms.slice().sort((a, b) => {
   if (a.key === detected) return -1;
   if (b.key === detected) return 1;
   return 0;
 });
 const platformsHtml = platforms.map(p => `
   <button class="btn btn-secondary platform-btn" data-key="${p.key}" style="margin-bottom:8px;display:flex;align-items:center;justify-content:space-between;gap:10px;">
     <span>${p.title}</span>
     ${p.key === detected ? '<span class="tg-chip">Рекомендуется</span>' : ''}
   </button>
 `).join('');
 content.innerHTML = `<p style="margin-bottom:12px;color:var(--hint-color);font-size:14px;">Выберите устройство:</p>${platformsHtml}`;

 const showPlatform = async (key) => {
   content.innerHTML = "<div class='loading'>Загрузка...</div>";
   try {
     const pData = await apiCall('/api/miniapp/connect/' + key);
     if (pData.error) throw new Error(pData.error);

     const stepsHtml = pData.steps.map((s, i) => `
       <div class="tg-step">
         <span class="tg-step__num">${i + 1}</span>
         <span class="tg-step__text">${s}</span>
       </div>
     `).join('');
     const subUrl = CURRENT_SUB_URL || (CURRENT_SUB_DATA && CURRENT_SUB_DATA.sub_url);
     const linkHtml = subUrl ? `
       <div class="tg-card">
         <div class="tg-card-title">Ссылка подписки</div>
         <div class="link-box" style="margin:0 0 10px;font-size:12px;">${subUrl}</div>
         <button class="btn btn-primary" id="connect-copy" style="margin-bottom:0;">Скопировать ссылку</button>
       </div>
     ` : `<div class="tg-note">Сначала получите подписку, чтобы скопировать ссылку.</div>`;

     content.innerHTML = `
       <h3 style="text-align:left;color:var(--text-color);margin-bottom:14px;font-size:18px;">${pData.title}</h3>
       <div class="tg-steps">${stepsHtml}</div>
       <a href="${pData.app_url}" target="_blank" id="connect-app-link" style="display:block;text-decoration:none;margin-top:16px;"><button class="btn btn-link" style="width:100%;">Скачать ${pData.app}</button></a>
       ${linkHtml}
       <button class="btn btn-secondary" id="connect-back" style="margin-top:8px;">Назад к списку</button>
     `;

     const copyBtn = document.getElementById('connect-copy');
     if (copyBtn) copyBtn.addEventListener('click', () => copyToClipboard(subUrl));
     document.getElementById('connect-back').addEventListener('click', () => openConnectModal());
   } catch (e) {
     content.innerHTML = `<div class="error">Ошибка: ${e.message}</div>`;
   }
 };

 content.querySelectorAll('.platform-btn').forEach(btn => {
   btn.addEventListener('click', () => showPlatform(btn.dataset.key));
 });
 } catch (e) { content.innerHTML = `<div class="error">Ошибка: ${e.message}</div>`; }
 }
 document.getElementById('connect-close').addEventListener('click', () => document.getElementById('connect-modal').classList.remove('show'));

 async function openTermsModal() {
 document.getElementById('terms-checkbox').checked = false;
 document.getElementById('terms-submit').disabled = true;
 document.getElementById('terms-modal').classList.add('show');
 const docsList = document.getElementById('terms-docs-list');
 docsList.innerHTML = '<div class="loading"> Загрузка документов...</div>';
 try {
 if (!CACHED_DOCS) {
 const data = await apiCall('/api/miniapp/profile');
 if (data.error) throw new Error(data.error);
 CACHED_DOCS = data.documents;
 }
 const linksHtml = CACHED_DOCS.map((d, i) => `<a href="#" class="term-doc-btn" data-index="${i}" style="display:block; padding:12px; background:var(--bg-color); border:1px solid var(--border-color); border-radius:8px; margin-bottom:8px; color:var(--link-color); text-decoration:none; text-align:center; font-size:14px;">${d.title}</a>`).join('');
 docsList.innerHTML = linksHtml;
 docsList.querySelectorAll('.term-doc-btn').forEach(btn => {
 btn.addEventListener('click', (e) => { e.preventDefault(); document.getElementById('terms-modal').classList.remove('show'); openDocsModal(parseInt(btn.dataset.index), true); });
 });
 } catch (e) { docsList.innerHTML = `<div class="error">Ошибка загрузки: ${e.message}</div>`; }
 }

 document.getElementById('terms-close').addEventListener('click', () => document.getElementById('terms-modal').classList.remove('show'));
 document.getElementById('terms-checkbox').addEventListener('change', (e) => { document.getElementById('terms-submit').disabled = !e.target.checked; });
 document.getElementById('terms-submit').addEventListener('click', async () => {
 const btn = document.getElementById('terms-submit');
 btn.disabled = true; btn.textContent = 'Отправка...';
 try {
 const data = await apiCall('/api/miniapp/accept_terms');
 if (data.error) throw new Error(data.error);
 document.getElementById('terms-modal').classList.remove('show');
 showToast('Заявка отправлена');
 loadMain();
 } catch (e) { showToast(' ' + e.message); btn.disabled = false; btn.textContent = 'Получить подписку'; }
 });

 // ==================== АДМИН-ПАНЕЛЬ ====================
 let ADMIN = { loaded: false, view: 'overview', page: 1, q: '', status: 'all', sort: 'created_desc', busy: false, timer: null };
 let MONITOR_STATE = { index: 0, count: 0, touchX: null, touchY: null, heightTimer: null };

 async function adminCall(path, body = {}) {
 const r = await apiCall('/api/miniapp/admin' + path, body);
 // toast убран — вызывающий код сам решает
 return r || {};
 }

 async function openXuiPanel(panelId = '') {
 const r = await adminCall('/xui', panelId ? { panel_id: panelId } : {});
 if (!r.url) {
   showToast(r.error || 'Не удалось получить ссылку на 3x-ui', true);
   return;
 }
 if (tg && typeof tg.openLink === 'function') {
   tg.openLink(r.url);
 } else {
   window.open(r.url, '_blank', 'noopener');
 }
 }

 function adminBadge(u) {
 if (u.status === 'pending') return '<span class="badge pending">заявка</span>';
 if (u.status === 'rejected') return '<span class="badge dead">отклонён</span>';
 if (!u.expires_at) return '';
 const today = new Date(); today.setHours(0, 0, 0, 0);
 const exp = new Date(u.expires_at + 'T00:00:00');
 if (isNaN(exp)) return '';
 const days = Math.ceil((exp - today) / 86400000);
 if (days < 0) return '<span class="badge dead">истёк</span>';
 if (days <= 3) return `<span class="badge warn">${days} дн.</span>`;
 return '';
 }

 function adminUserBadges(u, daysLeft) {
    const badges = [];
    if (u.vpn_online) badges.push('<span class="badge online">онлайн</span>');
    else badges.push('<span class="badge offline">офлайн</span>');
    if (u.status === 'pending') badges.push('<span class="badge pending">заявка</span>');
    if (u.status === 'blocked') badges.push('<span class="badge dead">заблокирован</span>');
    if (u.status === 'rejected') badges.push('<span class="badge dead">отклонён</span>');
    if (u.status === 'active' && daysLeft !== null) {
        if (daysLeft < 0) badges.push('<span class="badge dead">истёк</span>');
        else if (daysLeft <= 3) badges.push(`<span class="badge warn">${daysLeft} дн.</span>`);
    }
    if (u.source === 'web' || u.is_web) badges.push('<span class="badge web">web</span>');
    return badges.join('');
}

 function adminUserRow(u) {
    let daysLeft = null;
    if (u.expires_at) {
        const exp = new Date(String(u.expires_at).slice(0, 10) + 'T00:00:00');
        if (!isNaN(exp)) {
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            daysLeft = Math.ceil((exp - today) / 86400000);
        }
    }
    return `
    <div class="admin-user" data-tg="${u.telegram_id}">
        <div class="admin-user-info">
            <div class="admin-user-name">${u.first_name || '—'}${u.username ? ' <span class="admin-user-username">@' + u.username + '</span>' : ''}</div>
            <div class="admin-user-badges">${adminUserBadges(u, daysLeft)}</div>
        </div>
        <div class="admin-user-arrow">›</div>
    </div>`;
}

 function renderAdminAttention(r) {
 const el = document.getElementById('admin-attention');
 if (!el) return;
 const count = (value) => Number(value) || 0;
 el.innerHTML = `
  <button class="tg-item" onclick="setAdminStatus('pending')">
    <span>Заявки</span>
    <span class="tg-item__meta">${count(r.pending)}</span>
  </button>
  <button class="tg-item" onclick="openTickets()">
    <span>Тикеты без ответа</span>
    <span class="tg-item__meta">${count(r.tickets_unread)}</span>
  </button>
  <button class="tg-item" onclick="setAdminStatus('expiring')">
    <span>Истекают в ближайшие 3 дня</span>
    <span class="tg-item__meta">${count(r.expiring_3d)}</span>
  </button>
 `;
 }

 function renderAdminUsersSummary(r) {
 const el = document.getElementById('admin-users-summary');
 if (!el) return;
 const items = [
   { key: 'all', label: 'Все', count: r.users_total },
   { key: 'active', label: 'Активные', count: r.active },
   { key: 'pending', label: 'Заявки', count: r.pending },
   { key: 'expiring', label: 'Истекают', count: r.expiring_3d },
   { key: 'blocked', label: 'Заблокированные', count: r.blocked ?? 0 },
 ];
 el.innerHTML = items.map(item => `
   <button class="tab ${ADMIN.status === item.key ? 'active' : ''}" data-filter="${item.key}" onclick="setAdminStatus('${item.key}')">
     ${item.label} ${item.count}
   </button>
 `).join('');
 }

 async function loadAdminStats() {
 const r = await adminCall('/stats');
 if (r.error) return;
 const el = document.getElementById('admin-stats');
 if (!el) return;
 el.innerHTML = `
 <div class="stat-card"><div class="stat-num">${r.active}</div><div class="stat-lbl">Активных из ${r.max_users}</div></div>
 <div class="stat-card"><div class="stat-num" style="color:var(--success-color);">${r.online_count ?? 0}</div><div class="stat-lbl">Онлайн VPN</div></div>
 <div class="stat-card"><div class="stat-num">${r.pending}</div><div class="stat-lbl">Заявки</div></div>
 <div class="stat-card"><div class="stat-num">${r.tickets_unread ?? 0}</div><div class="stat-lbl">Тикеты без ответа</div></div>
 `;
 renderAdminAttention(r);
 renderAdminUsersSummary(r);
 const pendingBtn = document.getElementById('pending-count');
 if (pendingBtn) {
 if (r.pending > 0) {
 pendingBtn.textContent = r.pending; pendingBtn.style.display = 'inline-block';
 if (ADMIN.status !== 'pending') document.getElementById('filter-pending-btn').style.borderColor = 'var(--button-color)';
 } else {
 pendingBtn.style.display = 'none';
 document.getElementById('filter-pending-btn').style.borderColor = 'var(--border-color)';
 }
 updateAdminTabBadge((r.pending || 0) + (r.tickets_unread || 0));
 updateTicketsBadge(r.tickets_unread || 0);
 }
 }

 function updateTicketsBadge(count) {
 document.querySelectorAll('.admin-tickets-badge').forEach(badge => {
   if (count > 0) { badge.textContent = count; badge.style.display = 'inline-block'; }
   else badge.style.display = 'none';
 });
 }

 function fmtBytes(n) {
 if (n === null || n === undefined) return '—';
 const units = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ'];
 let v = Number(n) || 0;
 let i = 0;
 while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
 return `${v >= 100 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`;
 }

 function fmtUptime(sec) {
 if (sec === null || sec === undefined) return '—';
 const s = Math.max(0, Number(sec) || 0);
 const d = Math.floor(s / 86400);
 const h = Math.floor((s % 86400) / 3600);
 const m = Math.floor((s % 3600) / 60);
 if (d > 0) return `${d}д ${h}ч`;
 if (h > 0) return `${h}ч ${m}м`;
 return `${m}м`;
 }

 function monitorBarClass(pct) {
 if (pct >= 85) return 'bad';
 if (pct >= 70) return 'warn';
 return '';
 }

 function monitorMetric(label, value, pct) {
 const bar = (pct === null || pct === undefined)
  ? ''
  : `<div class="monitor-bar"><div class="monitor-bar__fill ${monitorBarClass(pct)}" style="width:${Math.min(100, Math.max(0, pct))}%"></div></div>`;
 return `<div class="monitor-metric"><div class="monitor-metric__label">${label}</div><div class="monitor-metric__value">${value}</div>${bar}</div>`;
 }

 function monitorSparkline(history, key, label, color) {
 const values = (history || [])
   .map(item => item[key])
   .filter(value => value !== null && value !== undefined && !isNaN(Number(value)))
   .map(Number);
 const last = values.length ? Math.round(values[values.length - 1]) : null;
 if (values.length < 2) {
   return `<div class="monitor-chart"><div class="monitor-chart__label">${label}<span>${last == null ? '—' : last + '%'}</span></div><div class="monitor-chart-empty" style="margin:0;">Мало данных</div></div>`;
 }
 const points = values.map((value, index) => {
   const x = (index / (values.length - 1)) * 100;
   const y = 26 - (Math.min(100, Math.max(0, value)) / 100) * 24;
   return `${x.toFixed(1)},${y.toFixed(1)}`;
 }).join(' ');
 const grid = '<line class="monitor-chart__grid" x1="0" y1="14" x2="100" y2="14"></line>';
 return `<div class="monitor-chart"><div class="monitor-chart__label">${label}<span>${last}%</span></div><svg viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true">${grid}<polyline points="${points}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg></div>`;
 }

 function monitorTrafficChart(history) {
 const values = (history || [])
   .map(item => Number(item.traffic_total))
   .filter(value => Number.isFinite(value));
 if (values.length < 2) {
   return `<div class="monitor-chart monitor-chart--wide"><div class="monitor-chart__label">Трафик за 24 часа<span>—</span></div><div class="monitor-chart-empty" style="margin:0;">Мало данных</div></div>`;
 }
 const deltas = [];
 for (let i = 1; i < values.length; i += 1) {
   const diff = values[i] - values[i - 1];
   deltas.push(diff > 0 ? diff : 0);
 }
 const total = deltas.reduce((sum, value) => sum + value, 0);
 const max = Math.max(...deltas, 1);
 const points = deltas.map((value, index) => {
   const x = (index / (deltas.length - 1)) * 100;
   const y = 26 - (value / max) * 24;
   return `${x.toFixed(1)},${y.toFixed(1)}`;
 }).join(' ');
 const grid = '<line class="monitor-chart__grid" x1="0" y1="14" x2="100" y2="14"></line>';
 return `<div class="monitor-chart monitor-chart--wide"><div class="monitor-chart__label">Трафик за 24 часа<span>${fmtBytes(total)}</span></div><svg viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true">${grid}<polyline points="${points}" fill="none" stroke="#8b5cf6" stroke-width="2" vector-effect="non-scaling-stroke"/></svg></div>`;
 }

 function renderMonitorSlide(r) {
 const ok = !!r.ok;
 const cpu = r.cpu_percent;
 const mem = r.mem_percent;
 const disk = r.disk_percent;
 const history = Array.isArray(r.history) ? r.history : [];
 const chartsHtml = `
  <div class="monitor-charts-head">История за 24 часа</div>
  <div class="monitor-charts">
    ${monitorSparkline(history, 'cpu_percent', 'CPU', '#31c46b')}
    ${monitorSparkline(history, 'mem_percent', 'RAM', '#e0a33a')}
    ${monitorSparkline(history, 'disk_percent', 'Диск', '#3390ec')}
     ${monitorTrafficChart(history)}
  </div>`;
 const stateText = ok ? 'онлайн' : 'ошибка';
 const panelId = escapeHtml(r.panel_id || '');
 const panelName = escapeHtml(r.panel_name || r.panel_id || '3x-ui');
 const footer = [
  `Xray: ${escapeHtml(r.xray_state || '—')}${r.xray_version ? ' ' + escapeHtml(r.xray_version) : ''}`,
  `Панель: ${escapeHtml(r.panel_version || '—')}`,
  `Uptime: ${fmtUptime(r.uptime)}`,
  `Сертификат: ${r.cert_days_left == null ? '—' : r.cert_days_left + ' дн.'}`,
  `API: ${r.api_ms == null ? '—' : r.api_ms + ' мс'}`,
  `Трафик: ${fmtBytes(r.traffic_total)}`,
 ].join(' · ');

 return `
  <div class="monitor-slide" data-panel-id="${panelId}">
   <div class="monitor-head">
    <div>
     <div class="monitor-title">${panelName}</div>
     <div class="monitor-state"><span class="monitor-dot ${ok ? 'ok' : 'bad'}"></span>${stateText} · ${formatAuditTime(r.checked_at)}</div>
    </div>
    <div class="monitor-head-actions">
     <button class="monitor-refresh" data-xui-panel="${panelId}" onclick="openXuiPanel(this.dataset.xuiPanel)">Панель</button>
    </div>
   </div>
   ${ok ? `
    <div class="monitor-grid">
     ${monitorMetric('CPU', cpu == null ? '—' : cpu + '%', cpu)}
     ${monitorMetric('RAM', r.mem_total ? `${fmtBytes(r.mem_used)} / ${fmtBytes(r.mem_total)}` : '—', mem)}
     ${monitorMetric('Диск', r.disk_total ? `${fmtBytes(r.disk_used)} / ${fmtBytes(r.disk_total)}` : '—', disk)}
     ${monitorMetric('Онлайн VPN', r.online_count == null ? '—' : r.online_count)}
    </div>
    ${chartsHtml}
    <div class="monitor-footer">${footer}</div>
   ` : `<div class="monitor-error">${escapeHtml(r.error || 'Панель не отвечает')}</div>`}
  </div>`;
 }

 function monitorUpdateDots(index) {
 const dots = document.querySelectorAll('#admin-monitor-dots .monitor-page-dot');
 dots.forEach((dot, i) => dot.classList.toggle('active', i === index));
 const hint = document.querySelector('.monitor-hint');
 if (hint) hint.textContent = `Свайп по кругу · ${index + 1}/${MONITOR_STATE.count}`;
 }

 function monitorPointerDown(e) {
 if (e.pointerType === 'mouse' && e.button !== 0) return;
 MONITOR_STATE.touchX = e.clientX;
 MONITOR_STATE.touchY = e.clientY;
 }

 function monitorPointerUp(e) {
 if (MONITOR_STATE.touchX == null) return;
 const dx = e.clientX - MONITOR_STATE.touchX;
 const dy = e.clientY - MONITOR_STATE.touchY;
 MONITOR_STATE.touchX = null;
 MONITOR_STATE.touchY = null;
 if (Math.abs(dx) < 40 || Math.abs(dx) < Math.abs(dy)) return;
 monitorGoTo(MONITOR_STATE.index + (dx < 0 ? 1 : -1));
 }

 function monitorResize() {
 const track = document.getElementById('admin-monitor-track');
 if (!track) return;
 const viewport = track.parentElement;
 const slides = track.querySelectorAll('.monitor-slide');
 const slide = slides[MONITOR_STATE.index];
 if (viewport && slide) viewport.style.height = slide.offsetHeight + 'px';
 }

 function monitorGoTo(index) {
 const track = document.getElementById('admin-monitor-track');
 if (!track || !MONITOR_STATE.count) return;
 const count = MONITOR_STATE.count;
 const previous = MONITOR_STATE.index;
 const next = ((Number(index) || 0) % count + count) % count;
 MONITOR_STATE.index = next;
 monitorUpdateDots(next);

 const slides = track.querySelectorAll('.monitor-slide');
 const viewport = track.parentElement;
 if (viewport) {
   const currentHeight = slides[previous] ? slides[previous].offsetHeight : 0;
   const targetHeight = slides[next] ? slides[next].offsetHeight : 0;
   viewport.style.height = Math.max(currentHeight, targetHeight) + 'px';
 }
 track.style.transform = `translateX(-${next * 100}%)`;

 if (viewport) {
   clearTimeout(MONITOR_STATE.heightTimer);
   MONITOR_STATE.heightTimer = setTimeout(() => {
     const target = slides[next];
     if (target) viewport.style.height = target.offsetHeight + 'px';
   }, 320);
 }
 }

 window.addEventListener('resize', monitorResize);

 function renderAdminMonitorSummary(panels, error) {
 const el = document.getElementById('admin-monitor-summary');
 if (!el) return;

 if (!panels || !panels.length) {
   el.innerHTML = `
     <button class="tg-item" onclick="switchAdminView('system')">
       <span>Серверы</span>
       <span class="tg-item__meta">${escapeHtml(error || 'Нет данных')}</span>
     </button>`;
 } else {
   el.innerHTML = panels.map(panel => {
     const ok = !!panel.ok;
     const name = escapeHtml(panel.panel_name || panel.panel_id || '3x-ui');
     const meta = ok
       ? `CPU ${panel.cpu_percent ?? '—'}% · RAM ${panel.mem_percent ?? '—'}%`
       : 'Ошибка';
     return `
       <button class="tg-item" onclick="switchAdminView('system')">
         <span>${name}</span>
         <span class="tg-item__meta">${meta}</span>
       </button>`;
   }).join('');
 }
 }

 async function loadAdminMonitor(force = false) {
 const el = document.getElementById('admin-monitor');
 if (!el) return;
 if (el.dataset.loading === '1' && !force) return;
 el.dataset.loading = '1';
 el.style.display = 'block';
 if (!el.innerHTML.trim() || force) el.innerHTML = '<div class="monitor-state"><span class="monitor-dot"></span> Загрузка метрик...</div>';

 let r;
 try {
  r = await adminCall('/monitor');
 } catch (e) {
  r = { error: e && e.message ? e.message : 'Нет ответа от панели' };
 }
 el.dataset.loading = '0';

 const panels = Array.isArray(r && r.panels)
  ? r.panels
  : (r && r.checked_at ? [r] : []);
 if (!panels.length) {
  renderAdminMonitorSummary([], (r && r.error) || 'Нет ответа от панелей');
  el.innerHTML = `
   <div class="monitor-head">
    <div class="monitor-title">Серверы 3x-ui</div>
    <button class="monitor-refresh" onclick="loadAdminMonitor(true)">Обновить</button>
   </div>
   <div class="monitor-error">${escapeHtml((r && r.error) || 'Нет ответа от панелей')}</div>`;
  return;
 }

 renderAdminMonitorSummary(panels, '');
 const previousIndex = MONITOR_STATE.index || 0;
 MONITOR_STATE.count = panels.length;
 MONITOR_STATE.index = Math.min(previousIndex, panels.length - 1);
 const slides = panels.map(renderMonitorSlide).join('');
 const dots = panels.length > 1
  ? `<div class="monitor-dots" id="admin-monitor-dots">
      ${panels.map((_, i) => `<button type="button" class="monitor-page-dot${i === MONITOR_STATE.index ? ' active' : ''}" onclick="monitorGoTo(${i})" aria-label="Панель ${i + 1}"></button>`).join('')}
     </div>
     <div class="monitor-hint">Свайп по кругу · ${MONITOR_STATE.index + 1}/${panels.length}</div>`
  : '';

 el.innerHTML = `
  <div class="monitor-head">
   <div class="monitor-title">Серверы 3x-ui</div>
   <button class="monitor-refresh" onclick="loadAdminMonitor(true)">Обновить</button>
  </div>
  <div class="monitor-viewport">
   <div class="monitor-track" id="admin-monitor-track">${slides}</div>
  </div>
  ${dots}`;

 const track = document.getElementById('admin-monitor-track');
 if (track) {
  const viewport = track.parentElement;
  if (viewport) {
    viewport.onpointerdown = (event) => {
      try { viewport.setPointerCapture(event.pointerId); } catch (_) {}
      monitorPointerDown(event);
    };
    viewport.onpointerup = monitorPointerUp;
    viewport.onpointercancel = monitorPointerUp;
  }
  track.style.transform = `translateX(-${MONITOR_STATE.index * 100}%)`;
  requestAnimationFrame(monitorResize);
 }
 monitorUpdateDots(MONITOR_STATE.index);
 }

 function openTickets() {
 const modal = document.getElementById('tickets-modal');
 if (!modal) return;
 TICKETS_STATE = { filter: 'active', current: null, busy: false };
 modal.classList.add('show');
 const closeBtn = document.getElementById('tickets-modal-close');
 if (closeBtn) closeBtn.onclick = closeTickets;
 loadAdminTickets();
 }

 function closeTickets() {
 const modal = document.getElementById('tickets-modal');
 if (modal) modal.classList.remove('show');
 TICKETS_STATE.current = null;
 }

 function setTicketFilter(filter) {
 TICKETS_STATE.filter = filter;
 loadAdminTickets();
 }

 function adminTicketRow(t) {
 const who = t.first_name || t.username || ('ID ' + t.telegram_id);
 const unread = t.unread_admin
  ? ' <span class="badge pending" style="margin-left:4px;">новый</span>'
  : '';
 return `
  <div class="ticket-row" onclick="openAdminTicket(${t.id})">
   <div class="ticket-row__top">
    <span>#${t.id} · ${escapeHtml(t.subject)}${unread}</span>
    <span class="ticket-row__arrow">›</span>
   </div>
   <div class="ticket-row__meta">${escapeHtml(who)}${t.username ? ' @' + escapeHtml(t.username) : ''} · ${escapeHtml(t.category_label)} · ${formatAuditTime(t.updated_at)}</div>
   <div class="ticket-row__last">${escapeHtml(t.last_text || '')}</div>
   <div style="margin-top:6px;">${supportStatusBadge(t.status)}</div>
  </div>`;
 }

 async function loadAdminTickets() {
 const el = document.getElementById('admin-tickets-content');
 if (!el) return;
 const f = TICKETS_STATE.filter;
 el.innerHTML = `
  <div class="ticket-toolbar">
   <button class="tab ${f === 'active' ? 'active' : ''}" onclick="setTicketFilter('active')">Активные</button>
   <button class="tab ${f === 'closed' ? 'active' : ''}" onclick="setTicketFilter('closed')">Закрытые</button>
   <button class="tab ${f === 'all' ? 'active' : ''}" onclick="setTicketFilter('all')">Все</button>
  </div>
  <div class="loading">Загрузка...</div>`;
 const r = await adminCall('/tickets', { status: f, limit: 50 });
 if (!el) return;
 if (r.error) { el.innerHTML = `<div class="monitor-error">${escapeHtml(r.error)}</div>`; return; }
 updateTicketsBadge(r.tickets_unread || 0);
 const list = r.tickets || [];
 el.innerHTML = `
  <div class="ticket-toolbar">
   <button class="tab ${f === 'active' ? 'active' : ''}" onclick="setTicketFilter('active')">Активные</button>
   <button class="tab ${f === 'closed' ? 'active' : ''}" onclick="setTicketFilter('closed')">Закрытые</button>
   <button class="tab ${f === 'all' ? 'active' : ''}" onclick="setTicketFilter('all')">Все</button>
  </div>
  ${list.length ? list.map(adminTicketRow).join('') : '<div class="ticket-empty">Тикетов нет</div>'}`;
 }

 async function openAdminTicket(id) {
 const el = document.getElementById('admin-tickets-content');
 if (!el) return;
 el.innerHTML = '<div class="loading">Загрузка...</div>';
 const r = await adminCall('/ticket', { ticket_id: id });
 if (!el) return;
 if (r.error) { el.innerHTML = `<div class="monitor-error">${escapeHtml(r.error)}</div>`; return; }
 TICKETS_STATE.current = r.ticket;
 renderAdminTicket(r);
 loadAdminStats();
 }

 function renderAdminTicket(data) {
 const el = document.getElementById('admin-tickets-content');
 if (!el) return;
 const t = data.ticket;
 const messages = data.messages || [];
 const who = t.first_name || t.username || ('ID ' + t.telegram_id);
 const msgs = messages.length
  ? messages.map(m => `
   <div class="ticket-msg ${m.sender === 'admin' ? 'admin' : 'user'}">
    <div class="ticket-msg__meta">${m.sender === 'admin' ? 'Поддержка' : escapeHtml(who)} · ${formatAuditTime(m.created_at)}</div>
    ${escapeHtml(m.text)}
   </div>`).join('')
  : '<div class="ticket-empty">Сообщений нет</div>';
 el.innerHTML = `
  <button class="ticket-back" onclick="loadAdminTickets()">← К списку</button>
  <div style="font-size:16px;font-weight:600;margin-bottom:4px;">#${t.id} · ${escapeHtml(t.subject)}</div>
  <div class="ticket-subtle">${escapeHtml(who)}${t.username ? ' @' + escapeHtml(t.username) : ''} · ID ${t.telegram_id} · ${escapeHtml(t.category_label)} · ${formatAuditTime(t.created_at)}</div>
  <div style="margin-top:8px;">${supportStatusBadge(t.status)}</div>
  <div class="ticket-divider"></div>
  <div class="ticket-msgs">${msgs}</div>
  <div class="ticket-form">
   <textarea id="admin-ticket-reply" class="ticket-textarea" maxlength="3000" placeholder="Ответ пользователю..."></textarea>
   <div class="ticket-actions">
    <button class="btn btn-primary" id="admin-ticket-reply-btn" onclick="sendAdminTicketReply()">Ответить</button>
    <button class="btn btn-secondary" onclick="closeAdminTicket()">Закрыть</button>
   </div>
  </div>
  ${t.status === 'closed' ? '<div class="ticket-subtle" style="margin-top:8px;">Тикет закрыт. Ответ снова откроет его.</div>' : ''}`;
 }

 async function sendAdminTicketReply() {
 if (!TICKETS_STATE.current) return;
 const el = document.getElementById('admin-ticket-reply');
 const btn = document.getElementById('admin-ticket-reply-btn');
 const text = (el.value || '').trim();
 if (text.length < 2) { showToast('Сообщение слишком короткое', true); el.focus(); return; }
 btn.disabled = true; btn.textContent = 'Отправляем...';
 const r = await adminCall('/ticket/reply', {
  ticket_id: TICKETS_STATE.current.id, text
 });
 btn.disabled = false; btn.textContent = 'Ответить';
 if (r.error) { showToast(r.error, true); return; }
 showToast('Ответ отправлен');
 await openAdminTicket(TICKETS_STATE.current.id);
 }

 async function closeAdminTicket() {
 if (!TICKETS_STATE.current) return;
 const ok = await showConfirm('Закрыть тикет? Пользователь получит уведомление.', 'Закрыть тикет');
 if (!ok) return;
 const r = await adminCall('/ticket/close', {
  ticket_id: TICKETS_STATE.current.id
 });
 if (r.error) { showToast(r.error, true); return; }
 showToast('Тикет закрыт');
 loadAdminTickets();
 loadAdminStats();
 }

 async function loadAdminUsers({ append = false } = {}) {
 if (ADMIN.busy) return;
 ADMIN.busy = true;
 const box = document.getElementById('admin-users');
 if (!box) { ADMIN.busy = false; return; }
 if (!append) {
   ADMIN.page = 1;
   box.innerHTML = '<div class="admin-empty">Загрузка...</div>';
 }
 try {
   const r = await adminCall('/users', {
     q: ADMIN.q,
     status: ADMIN.status,
     sort: ADMIN.sort,
     page: ADMIN.page,
     limit: 20,
   });
   if (r.error) {
     box.innerHTML = `<div class="admin-empty">${r.error}</div>`;
     return;
   }
   if (!append) box.innerHTML = '';
   box.insertAdjacentHTML('beforeend', (r.items || []).map(adminUserRow).join(''));
   const more = document.getElementById('admin-more');
   if (more) more.style.display = r.has_more ? 'block' : 'none';
   if (!append && !(r.items || []).length) {
     box.innerHTML = `
       <div class="admin-empty">
         Нет пользователей по этому фильтру.<br>
         <button class="btn btn-secondary" style="margin-top:10px;" onclick="showAllUsers()">Показать всех</button>
       </div>`;
   }
 } catch (e) {
   box.innerHTML = `<div class="admin-empty">Ошибка загрузки: ${e.message}</div>`;
 } finally {
   ADMIN.busy = false;
 }
 }

 

async function openAdminUserCard(tgId) {
 try {
 const r = await adminCall('/user', { tg_id: tgId });
 if (r.error) { showToast(r.error, true); return; }

 const modal = document.getElementById('admin-user-modal');
 const container = document.getElementById('admin-user-content');
 if (!modal || !container) { showToast('Модалка не найдена', true); return; }

 const u = r.user || r;
 const statusMap = { active: 'Активна', pending: 'Заявка', rejected: 'Отклонён', new: 'Новая', blocked: 'Заблокирована' };
 const statusText = statusMap[u.status] || u.status;
 const isBlocked = u.is_blocked || false;

 let daysBar = '';
 if (u.days_left !== null && u.days_left !== undefined && u.days_left >= 0) {
 const totalDays = 30;
 const percent = Math.min(100, (u.days_left / totalDays) * 100);
 const color = u.days_left <= 3 ? '#f85149' : (u.days_left <= 7 ? '#d29922' : '#238636');
 daysBar = `
 <div style="margin-top:8px;">
 <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--hint-color);margin-bottom:4px;">
 <span>Осталось дней</span><span>${u.days_left} из ${totalDays}</span>
 </div>
 <div class="progress-container" style="height:6px;">
 <div class="progress-fill" style="width:${percent}%;background-color:${color};"></div>
 </div>
 </div>`;
 }

 const commentHtml = u.comment
 ? `<div class="user-card-comment">${u.comment}</div>`
 : `<div class="user-card-comment" style="color:var(--hint-color);font-style:italic;">Нет комментария</div>`;

 const trafficHtml = (u.traffic_up || u.traffic_down)
 ? `<div class="user-card-row"><span class="label">Трафик</span><span class="value">${u.traffic_down || '0 GB'} / ${u.traffic_up || '0 GB'}</span></div>`
 : '';

 let actionsHtml = '';
 if (u.status === 'pending') {
 actionsHtml = `<div class="user-card-actions-row">
 <button class="btn-extend" data-act="approve" data-tg="${tgId}">Одобрить</button>
 <button class="btn-reject" data-act="reject" data-tg="${tgId}">Отклонить</button>
 </div>`;
 } else if (isBlocked) {
 actionsHtml = `<div class="user-card-actions-row">
 <button class="btn-unblock" data-act="unblock" data-tg="${tgId}">Разблокировать</button>
 <button class="btn-delete" data-act="delete" data-tg="${tgId}">Удалить</button>
 </div>`;
 } else {
 actionsHtml = `<div class="user-card-actions-row">
 <button class="btn-extend" data-act="extend" data-tg="${tgId}">Продлить +30</button>
 </div>
 <div class="user-card-actions-row">
 <button class="btn-block" data-act="block" data-tg="${tgId}">Заблокировать</button>
 <button class="btn-delete" data-act="delete" data-tg="${tgId}">Удалить</button>
 </div>`;
 }

 const isOnline = u.vpn_online === true;
 const cardBadges = adminUserBadges(u, u.days_left ?? null);

 container.innerHTML = `
 <div class="user-card-header">
 <div class="user-card-name"><span>${u.first_name || 'Пользователь'}</span></div>
 <div class="admin-user-badges">${cardBadges}</div>
 <div class="user-card-meta" style="display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-top:8px;">
 <span onclick="copyToClipboard('@${u.username || ''}')" style="cursor:pointer; text-decoration:underline; text-decoration-style:dotted;">
 @${u.username || '—'}
 </span>
 <span style="cursor:pointer; text-decoration:underline; text-decoration-style:dotted;" onclick="copyToClipboard('${u.telegram_id}')">
 ID: ${u.telegram_id}
 </span>
 </div>
 </div>
 <div class="user-card-status">
 <span class="status-badge ${isBlocked ? 'expired' : (u.status === 'active' ? 'active' : 'pending')}">${statusText}${u.expires_at ? ' до ' + u.expires_at : ''}</span>
 ${daysBar}
 </div>
 <div class="user-card-row"><span class="label">Email</span><span class="value">${u.xui_email || '—'}</span></div>
 <div class="user-card-row"><span class="label">VPN</span><span class="value">${isOnline ? 'Онлайн' : 'Офлайн'}</span></div>
 <div class="user-card-row"><span class="label">Приглашено</span><span class="value">${u.invites_count || 0}</span></div>
 <div class="user-card-row"><span class="label">Продлений</span><span class="value">${u.renew_count || 0}</span></div>
 <div class="user-card-row"><span class="label">Последний визит</span><span class="value">${u.last_seen || '—'}</span></div>
 <div class="user-card-row"><span class="label">Регистрация</span><span class="value">${u.created_at || '—'}</span></div>
 ${trafficHtml}
 ${commentHtml}
 <div class="user-card-actions">${actionsHtml}</div>
 <div class="tg-card" style="margin-top:12px;">
   <div class="tg-card-title">Диагностика</div>
   <div id="admin-diag-result" class="tg-note" style="padding:0 0 8px;">Проверьте состояние клиента и ссылки подписки.</div>
   <button class="btn btn-secondary" id="admin-diag-run" style="margin-bottom:0;">Проверить подключение</button>
 </div>
 <button class="btn btn-secondary" style="width:100%; margin-top:12px;" onclick="openAuditForUser(${tgId})">История действий</button>
 `;

 container.querySelectorAll('[data-act]').forEach(btn => {
 btn.addEventListener('click', async () => {
 const act = btn.dataset.act;
 const id = +btn.dataset.tg;

 if (act === 'approve') {
 if (!await showConfirm('Одобрить заявку?')) return;
 const res = await adminCall('/approve', { tg_id: id });
 if (res.success) { showToast('Одобрен'); modal.classList.remove('show'); loadAdminUsers(); loadAdminStats(); }
 } else if (act === 'reject') {
 if (!await showConfirm('Отклонить заявку?')) return;
 const res = await adminCall('/reject', { tg_id: id });
 if (res.success) { showToast('Отклонён'); modal.classList.remove('show'); loadAdminUsers(); loadAdminStats(); }
 } else if (act === 'extend') {
 if (!await showConfirm('Продлить на 30 дней?')) return;
 const res = await adminCall('/extend', { tg_id: id, days: 30 });
 if (res.success) { showToast('Продлён'); modal.classList.remove('show'); loadAdminUsers(); loadAdminStats(); }
 } else if (act === 'delete') {
 if (!await showConfirm('Удалить пользователя?')) return;
 const res = await adminCall('/delete', { tg_id: id });
 if (res.success) { showToast('Удалён'); modal.classList.remove('show'); loadAdminUsers(); loadAdminStats(); }
 } else if (act === 'block') {
 if (!await showConfirm('Заблокировать пользователя?')) return;
 const res = await adminCall('/block', { tg_id: id });
 if (res.success) { showToast('Заблокирован'); modal.classList.remove('show'); loadAdminUsers(); loadAdminStats(); }
 } else if (act === 'unblock') {
 if (!await showConfirm('Разблокировать пользователя?')) return;
 const res = await adminCall('/unblock', { tg_id: id });
 if (res.success) { showToast('Разблокирован'); modal.classList.remove('show'); loadAdminUsers(); loadAdminStats(); }
 }
 });
 });

 const diagBtn = container.querySelector('#admin-diag-run');
 if (diagBtn) diagBtn.addEventListener('click', () => runAdminDiagnostics(tgId));

 document.getElementById('admin-user-close').onclick = () => modal.classList.remove('show');
 modal.classList.add('show');
 } catch (e) {
 console.error('openAdminUserCard error:', e);
 showToast('Ошибка: ' + e.message, true);
 }
 }

 async function runAdminDiagnostics(tgId) {
 const result = document.getElementById('admin-diag-result');
 const btn = document.getElementById('admin-diag-run');
 if (!result || !btn) return;

 btn.disabled = true;
 btn.textContent = 'Проверяем...';
 result.textContent = 'Проверяем состояние подключения.';

 try {
   const data = await adminCall('/diagnostics', { tg_id: tgId });
   if (data.error) {
     result.innerHTML = `<span class="tg-value-bad">${data.error}</span>`;
     return;
   }

   const mark = (value) => value ? 'tg-value-ok' : 'tg-value-bad';
   const yesNo = (value) => value ? 'Да' : 'Нет';
   const linkLabel = data.sub_link_ok
     ? 'Доступна'
     : (data.sub_http_status ? `HTTP ${data.sub_http_status}` : 'Ошибка');

   result.innerHTML = `
     <div class="tg-list tg-list--flush">
       <div class="tg-item tg-item--static">
         <span class="tg-item__label">Панель</span>
         <span class="tg-item__value ${mark(data.panel_ok)}">${data.panel_ok ? 'Доступна' : 'Ошибка'}</span>
       </div>
       <div class="tg-item tg-item--static">
         <span class="tg-item__label">Сервер</span>
         <span class="tg-item__value">${data.panel_name || '—'}</span>
       </div>
       <div class="tg-item tg-item--static">
         <span class="tg-item__label">Клиент в панели</span>
         <span class="tg-item__value ${mark(data.client_found)}">${yesNo(data.client_found)}</span>
       </div>
       <div class="tg-item tg-item--static">
         <span class="tg-item__label">Клиент включён</span>
         <span class="tg-item__value ${mark(data.enabled)}">${yesNo(data.enabled)}</span>
       </div>
       <div class="tg-item tg-item--static">
         <span class="tg-item__label">Ссылка подписки</span>
         <span class="tg-item__value ${mark(data.sub_link_ok)}">${linkLabel}</span>
       </div>
       <div class="tg-item tg-item--static">
         <span class="tg-item__label">Подключение</span>
         <span class="tg-item__value ${mark(data.is_online)}">${data.is_online ? 'Онлайн' : 'Оффлайн'}</span>
       </div>
     </div>
     <div class="tg-note" style="padding:8px 0 0;">Проверено в ${data.checked_at}. ${data.is_online ? 'Устройство сейчас на связи.' : 'Если VPN не работает, проверьте приложение и выбранный сервер.'}</div>
   `;
 } catch (e) {
   result.innerHTML = `<span class="tg-value-bad">${e.message}</span>`;
 } finally {
   btn.disabled = false;
   btn.textContent = 'Проверить подключение';
 }
 }

 function switchAdminView(view) {
 ADMIN.view = view;
 document.querySelectorAll('#admin-subtabs .tab').forEach(tab => {
   tab.classList.toggle('active', tab.dataset.adminView === view);
 });
 document.querySelectorAll('.admin-view').forEach(section => {
   section.style.display = section.id === 'admin-view-' + view ? 'block' : 'none';
 });
 if (view === 'overview') loadAdminStats();
 else if (view === 'users') loadAdminUsers();
 else if (view === 'system') {
   loadAdminMonitor().then(() => requestAnimationFrame(monitorResize));
 }
 }

 function setAdminStatus(status) {
 ADMIN.status = status;
 document.querySelectorAll('#admin-filter-scroll .tab').forEach(tab => {
   tab.classList.toggle('active', tab.dataset.filter === status);
 });
 document.querySelectorAll('#admin-users-summary .tab').forEach(tab => {
   tab.classList.toggle('active', tab.dataset.filter === status);
 });
 switchAdminView('users');
 }

 function showAllUsers() {
 ADMIN.status = 'all';
 ADMIN.q = '';
 const search = document.getElementById('admin-q');
 if (search) search.value = '';
 document.querySelectorAll('#admin-filter-scroll .tab').forEach(tab => {
   tab.classList.toggle('active', tab.dataset.filter === 'all');
 });
 document.querySelectorAll('#admin-users-summary .tab').forEach(tab => {
   tab.classList.toggle('active', tab.dataset.filter === 'all');
 });
 switchAdminView('users');
 }

 async function syncAdminUsers() {
 const btn = document.getElementById('admin-sync');
 if (btn) { btn.dataset.loading = '1'; btn.disabled = true; }
 const r = await adminCall('/sync');
 if (btn) { delete btn.dataset.loading; btn.disabled = false; }
 if (r.success) {
   showToast(`Синхронизировано: ${r.updated}`);
   loadAdminUsers();
   loadAdminStats();
   loadAdminMonitor(true);
 } else {
   showToast(r.error || 'Не удалось синхронизировать', true);
 }
 }

 function renderAdminScreen() {
 document.getElementById('admin-content').innerHTML = `
 <div class="admin-subtabs" id="admin-subtabs">
   <button class="tab active" data-admin-view="overview" onclick="switchAdminView('overview')">Обзор</button>
   <button class="tab" data-admin-view="users" onclick="showAllUsers()">Пользователи</button>
   <button class="tab" data-admin-view="system" onclick="switchAdminView('system')">Система</button>
 </div>

 <div class="admin-view" id="admin-view-overview">
   <div class="stats-grid" id="admin-stats"></div>
   <div class="admin-section">
     <div class="admin-section-title">Требует внимания</div>
     <div class="tg-list" id="admin-attention"></div>
   </div>
   <div class="admin-section">
     <div class="admin-section-title">Серверы</div>
     <div class="tg-list" id="admin-monitor-summary"></div>
   </div>
   <div class="admin-section">
     <div class="admin-section-title">Быстрые действия</div>
     <div class="tg-list">
       <button class="tg-item" onclick="openBroadcast()"><span>Создать рассылку</span><span class="tg-item__arrow">›</span></button>
       <button class="tg-item" onclick="openTickets()"><span>Тикеты <span class="badge pending admin-tickets-badge" style="display:none;margin-left:4px;">0</span></span><span class="tg-item__arrow">›</span></button>
       <button class="tg-item" onclick="openAudit()"><span>История действий</span><span class="tg-item__arrow">›</span></button>
       <button class="tg-item" onclick="switchAdminView('system')"><span>Серверы и инструменты</span><span class="tg-item__arrow">›</span></button>
     </div>
   </div>
 </div>

 <div class="admin-view" id="admin-view-users" style="display:none;">
   <div class="admin-users-summary" id="admin-users-summary"></div>
   <div class="admin-search">
     <input id="admin-q" placeholder="Поиск: ID / @username / имя">
     <div class="admin-sort" id="admin-sort">
       <button type="button" class="admin-sort__btn" id="admin-sort-btn">Новые <span class="admin-sort__arrow">▼</span></button>
       <div class="admin-sort__list" id="admin-sort-list" hidden>
         <button type="button" data-value="created_desc">Новые</button>
         <button type="button" data-value="created_asc">Старые</button>
         <button type="button" data-value="name">По имени</button>
         <button type="button" data-value="expires">По сроку</button>
       </div>
     </div>
     <button id="admin-sync" class="admin-sync" title="Обновить даты из 3x-ui">
       <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
         <polyline points="23 4 23 10 17 10"></polyline>
         <polyline points="1 20 1 14 7 14"></polyline>
         <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
       </svg>
     </button>
   </div>
   <div class="tabs" id="admin-filter-scroll">
     <button class="tab active" data-filter="all" onclick="setAdminStatus('all')">Все</button>
     <button class="tab" data-filter="active" onclick="setAdminStatus('active')">Активные</button>
     <button class="tab" data-filter="pending" id="filter-pending-btn" onclick="setAdminStatus('pending')">Заявки <span class="badge pending" id="pending-count" style="display:none;">0</span></button>
     <button class="tab" data-filter="expiring" onclick="setAdminStatus('expiring')">Истекают</button>
     <button class="tab" data-filter="blocked" onclick="setAdminStatus('blocked')">Заблокированные</button>
     <button class="tab" data-filter="rejected" onclick="setAdminStatus('rejected')">Отклонённые</button>
   </div>
   <div class="card" style="padding:0;" id="admin-users"></div>
   <button class="btn btn-secondary" id="admin-more" style="width:100%;display:none;margin-top:8px;">Показать ещё</button>
 </div>

 <div class="admin-view" id="admin-view-system" style="display:none;">
   <div class="monitor-card" id="admin-monitor"></div>
   <div class="admin-section">
     <div class="admin-section-title">Инструменты</div>
     <div class="tg-list">
       <button class="tg-item" onclick="syncAdminUsers()"><span>Синхронизировать с 3x-ui</span><span class="tg-item__meta">Обновить даты</span></button>
       <button class="tg-item" onclick="openAudit()"><span>История действий</span><span class="tg-item__arrow">›</span></button>
       <button class="tg-item" onclick="openBroadcast()"><span>Массовая рассылка</span><span class="tg-item__arrow">›</span></button>
       <button class="tg-item" onclick="openTickets()"><span>Тикеты <span class="badge pending admin-tickets-badge" style="display:none;margin-left:4px;">0</span></span><span class="tg-item__arrow">›</span></button>
     </div>
   </div>
 </div>
 `;

 document.getElementById('admin-q').addEventListener('input', (e) => {
 clearTimeout(ADMIN._t);
 ADMIN._t = setTimeout(() => { ADMIN.q = e.target.value.trim(); loadAdminUsers(); }, 300);
 });
 document.getElementById('admin-sync').addEventListener('click', syncAdminUsers);

 // Кастомный select сортировки
 (function () {
   const btn = document.getElementById('admin-sort-btn');
   const list = document.getElementById('admin-sort-list');
   if (!btn || !list) return;
   const labels = { created_desc: 'Новые', created_asc: 'Старые', name: 'По имени', expires: 'По сроку' };
   const close = () => { list.hidden = true; };
   btn.addEventListener('click', (e) => {
     e.stopPropagation();
     list.hidden = !list.hidden;
   });
   list.querySelectorAll('button[data-value]').forEach(b => {
     b.addEventListener('click', (e) => {
       e.stopPropagation();
       ADMIN.sort = b.dataset.value;
       btn.childNodes[0].textContent = (labels[b.dataset.value] || b.textContent) + ' ';
       list.querySelectorAll('button').forEach(x => x.classList.remove('is-active'));
       b.classList.add('is-active');
       close();
       loadAdminUsers();
     });
   });
   document.addEventListener('click', (e) => {
     if (!list.hidden && !e.target.closest('#admin-sort')) close();
   });
 })();

 document.getElementById('admin-more').addEventListener('click', () => { ADMIN.page += 1; loadAdminUsers({ append: true }); });
 
 document.getElementById('admin-users').addEventListener('click', async (e) => {
 const row = e.target.closest('.admin-user');
 if (!row) return;
 const tgId = +row.dataset.tg;
 openAdminUserCard(tgId);
 });

 loadAdminStats();
 loadAdminMonitor();
 loadAdminUsers();
 }

 async function loadAdmin() {
 // Авто-обновление статистики каждые 30 секунд
 if (!window._adminInterval) {
   window._adminInterval = setInterval(() => {
     if (document.getElementById('admin-stats')) {
       loadAdminStats();
     }
   }, 30000);
   console.log('[admin] auto-refresh stats: 30s');
 }
 if (!window._monitorInterval) {
   window._monitorInterval = setInterval(() => {
     if (document.getElementById('admin-monitor') &&
         document.getElementById('screen-admin').classList.contains('active')) {
       loadAdminMonitor();
     }
   }, 30000);
   console.log('[admin] auto-refresh monitor: 30s');
 }

 if (!IS_ADMIN) return;
 document.getElementById('admin-loading').style.display = 'none';
 document.getElementById('admin-content').style.display = 'block';
 if (!ADMIN.loaded) { renderAdminScreen(); ADMIN.loaded = true; }
 else { loadAdminStats(); loadAdminMonitor(); loadAdminUsers(); }
 if (ADMIN.timer) clearInterval(ADMIN.timer);
 ADMIN.timer = setInterval(() => {
 if (!document.getElementById('screen-admin').classList.contains('active')) { clearInterval(ADMIN.timer); ADMIN.timer = null; return; }
 loadAdminStats();
 }, 60000);
 }

 // Запуск
 loadMain();



 // Делегирование: ловит #stars-close даже если элемент появился позже скрипта
 document.addEventListener('click', (e) => {
 if (e.target && e.target.closest && e.target.closest('#stars-close')) {
 document.getElementById('stars-modal').classList.remove('show');
 }
 });

 // Функция покупки звёзд
 async function buyStars(amount) {
 const modal = document.getElementById('stars-modal');
 try {
 const res = await fetch('/api/miniapp/invoice', { 
 method: 'POST', 
 headers: {'Content-Type': 'application/json'}, 
 body: JSON.stringify({init_data: tg.initData, amount: amount}) 
 });
 const invData = await res.json();
 if (invData.error) throw new Error(invData.error);
 
 tg.openInvoice(invData.invoice_link, (status) => {
 if (status === 'paid') showToast('Спасибо за поддержку!');
 else if (status === 'failed') showToast('Ошибка оплаты');
 modal.classList.remove('show');
 });
 } catch (e) { 
 showToast('Ошибка: ' + e.message); 
 }
 }

function buyStarsCustom() {
  const input = document.getElementById('custom-stars');
  const n = parseInt(input.value, 10);
  if (!n || n < 1 || n > 10000) {
    showToast('Введите сумму от 1 до 10000');
    input.focus();
    return;
  }
  buyStars(n);
}

document.addEventListener('click', (e) => {
  if (e.target && e.target.closest && e.target.closest('#custom-stars-btn')) {
    const row = document.getElementById('custom-stars-row');
    if (row) {
      row.style.display = 'flex';
      const inp = document.getElementById('custom-stars');
      if (inp) inp.focus();
    }
  }
});
