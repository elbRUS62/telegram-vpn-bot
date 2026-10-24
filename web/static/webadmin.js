(function () {
  "use strict";

  const CONFIG = window.WEBADMIN || {};
  const state = {
    view: "overview",
    users: { page: 1, q: "", status: "all", hasMore: false },
    tickets: { status: "active" },
  };

  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));

  function toast(message, kind = "ok") {
    const el = $("wa-toast");
    if (!el) return;
    el.textContent = message || "";
    el.className = "wa-toast" + (kind === "error" ? " is-error" : kind === "ok" ? " is-ok" : "");
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => { el.textContent = ""; el.className = "wa-toast"; }, 4000);
  }

  async function api(path, body = {}) {
    const response = await fetch("/api/miniapp/admin" + path, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": CONFIG.csrf || "",
      },
      body: JSON.stringify(body),
    });

    if (response.status === 401) {
      window.location.href = "/admin/login";
      throw new Error("Сессия истекла");
    }

    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok || data.error) {
      throw new Error(data.error || "Ошибка запроса");
    }
    return data;
  }

  function statusBadge(status) {
    const map = {
      active: ["Активна", "good"],
      pending: ["Заявка", "warn"],
      blocked: ["Заблокирована", "bad"],
      rejected: ["Отклонена", "bad"],
      expired: ["Истекла", "bad"],
      open: ["Открыт", "warn"],
      answered: ["Есть ответ", "good"],
      closed: ["Закрыт", "muted"],
    };
    const [label, kind] = map[status] || [status || "—", "muted"];
    return `<span class="wa-badge wa-badge-${kind}">${esc(label)}</span>`;
  }

  function roleBadge(role) {
    if (role === "superadmin") return '<span class="wa-badge wa-badge-role">Суперадмин</span>';
    if (role === "admin") return '<span class="wa-badge wa-badge-role">Админ</span>';
    return "";
  }

  function openModal(title, html) {
    $("wa-modal-title").textContent = title;
    $("wa-modal-body").innerHTML = html;
    $("wa-modal").hidden = false;
    document.body.style.overflow = "hidden";
    $("wa-modal-close").focus();
  }

  function closeModal() {
    $("wa-modal").hidden = true;
    $("wa-modal-body").innerHTML = "";
    document.body.style.overflow = "";
  }

  function showView(view) {
    state.view = view;
    document.querySelectorAll(".wa-nav-item").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.view === view);
    });
    document.querySelectorAll(".wa-view").forEach((section) => {
      section.hidden = section.id !== "view-" + view;
    });
    const titles = { overview: "Обзор", users: "Пользователи", tickets: "Тикеты", admins: "Админы", audit: "Аудит" };
    $("wa-title").textContent = titles[view] || "Админка";
    if (view === "overview") loadOverview();
    if (view === "users") loadUsers(1);
    if (view === "tickets") loadTickets();
    if (view === "admins") loadAdmins();
    if (view === "audit") loadAudit();
  }

  async function loadOverview() {
    $("wa-stats").innerHTML = '<div class="wa-empty">Загрузка...</div>';
    try {
      const [stats, monitor] = await Promise.all([
        api("/stats"),
        api("/monitor", { hours: 24 }).catch(() => ({ panels: [] })),
      ]);

      const cards = [
        ["Всего пользователей", stats.users_total, `Активных: ${stats.active}`],
        ["Заявки", stats.pending, `Истекают: ${stats.expiring_3d}`],
        ["Тикеты", stats.tickets_unread, `Открытых: ${stats.tickets_open}`],
        ["Онлайн", stats.online_count, `Трафик: ${stats.traffic_gb ?? "—"} ГБ`],
      ];
      $("wa-stats").innerHTML = cards.map(([label, value, meta]) => `
        <div class="wa-card">
          <div class="wa-card-label">${esc(label)}</div>
          <div class="wa-card-value">${esc(value ?? 0)}</div>
          <div class="wa-card-meta">${esc(meta)}</div>
        </div>`).join("");

      const attention = [];
      if (stats.pending) attention.push(["Заявки на подписку", `${stats.pending} ожидают решения`]);
      if (stats.tickets_unread) attention.push(["Новые ответы в тикетах", `${stats.tickets_unread} без ответа`]);
      if (stats.expiring_3d) attention.push(["Истекают в ближайшие 3 дня", `${stats.expiring_3d} пользователей`]);
      if (stats.free_slots <= 5) attention.push(["Свободные слоты", `${stats.free_slots} из ${stats.max_users}`]);
      $("wa-attention").innerHTML = attention.length
        ? attention.map(([title, meta]) => `<div class="wa-list-row"><div class="wa-list-main"><strong>${esc(title)}</strong><div class="wa-list-meta">${esc(meta)}</div></div></div>`).join("")
        : '<div class="wa-empty">Всё в порядке, срочных задач нет.</div>';

      const panels = Array.isArray(monitor.panels) ? monitor.panels : [];
      $("wa-monitor").innerHTML = panels.length
        ? panels.map((panel) => {
            const ok = panel.ok !== false;
            const name = panel.name || panel.id || "Сервер";
            const detail = panel.error ? panel.error : (ok ? "Доступен" : "Недоступен");
            return `<div class="wa-list-row"><div class="wa-list-main"><strong>${esc(name)}</strong><div class="wa-list-meta">${esc(detail)}</div></div><span class="wa-badge wa-badge-${ok ? "good" : "bad"}">${ok ? "Онлайн" : "Ошибка"}</span></div>`;
          }).join("")
        : '<div class="wa-empty">Нет данных мониторинга.</div>';
    } catch (error) {
      toast(error.message, "error");
      $("wa-stats").innerHTML = `<div class="wa-empty">${esc(error.message)}</div>`;
    }
  }

  async function loadUsers(page = 1) {
    state.users.page = page;
    const target = $("wa-users");
    target.innerHTML = '<div class="wa-table-empty">Загрузка...</div>';
    try {
      const data = await api("/users", {
        q: state.users.q,
        status: state.users.status,
        page,
        limit: 20,
        sort: "created_desc",
      });
      state.users.hasMore = !!data.has_more;
      $("wa-users-page").textContent = `Страница ${data.page || page} · всего ${data.total || 0}`;
      $("wa-users-prev").disabled = page <= 1;
      $("wa-users-next").disabled = !data.has_more;

      const items = data.items || [];
      if (!items.length) {
        target.innerHTML = '<div class="wa-table-empty">Пользователи не найдены.</div>';
        return;
      }

      target.innerHTML = `
        <table class="wa-table">
          <thead><tr><th>Пользователь</th><th>Статус</th><th>Срок</th><th>Роль</th><th></th></tr></thead>
          <tbody>${items.map((user) => `
            <tr>
              <td>
                <strong>${esc(user.first_name || "—")}</strong>
                <div class="wa-list-meta">${user.username ? "@" + esc(user.username) + " · " : ""}${esc(user.telegram_id)}</div>
              </td>
              <td>${statusBadge(user.status)}</td>
              <td>${esc(user.expires_at || "—")}<div class="wa-list-meta">${user.renew_count || 0} продлений</div></td>
              <td>${roleBadge(user.admin_role) || '<span class="wa-muted">—</span>'}</td>
              <td><button class="wa-button wa-button-secondary" data-user-open="${esc(user.telegram_id)}">Открыть</button></td>
            </tr>`).join("")}</tbody>
        </table>`;
    } catch (error) {
      toast(error.message, "error");
      target.innerHTML = `<div class="wa-table-empty">${esc(error.message)}</div>`;
    }
  }

  async function openUser(tgId) {
    try {
      const data = await api("/user", { tg_id: Number(tgId) });
      const user = data.user || data;
      const isBlocked = !!user.is_blocked || user.status === "blocked";
      const canDelete = CONFIG.isSuperadmin;
      const actions = [];

      if (user.status === "pending") {
        actions.push(`<button class="wa-button wa-button-primary" data-user-action="approve" data-tg="${esc(tgId)}">Одобрить</button>`);
        actions.push(`<button class="wa-button wa-button-danger" data-user-action="reject" data-tg="${esc(tgId)}">Отклонить</button>`);
      } else if (isBlocked) {
        actions.push(`<button class="wa-button wa-button-secondary" data-user-action="unblock" data-tg="${esc(tgId)}">Разблокировать</button>`);
      } else {
        actions.push(`<button class="wa-button wa-button-secondary" data-user-action="extend" data-tg="${esc(tgId)}">Продлить на 30 дней</button>`);
        actions.push(`<button class="wa-button wa-button-danger" data-user-action="block" data-tg="${esc(tgId)}">Заблокировать</button>`);
      }
      if (canDelete) {
        actions.push(`<button class="wa-button wa-button-danger" data-user-action="delete" data-tg="${esc(tgId)}">Удалить</button>`);
      }

      openModal(user.first_name || "Пользователь", `
        <div class="wa-detail-grid">
          <div class="wa-detail"><span>Telegram</span><strong>${user.username ? "@" + esc(user.username) : esc(user.telegram_id)}</strong></div>
          <div class="wa-detail"><span>ID</span><strong>${esc(user.telegram_id)}</strong></div>
          <div class="wa-detail"><span>Статус</span><strong>${statusBadge(user.status)}</strong></div>
          <div class="wa-detail"><span>Срок</span><strong>${esc(user.expires_at || "—")}</strong></div>
          <div class="wa-detail"><span>Email в панели</span><strong>${esc(user.xui_email || "—")}</strong></div>
          <div class="wa-detail"><span>Осталось дней</span><strong>${esc(user.days_left ?? "—")}</strong></div>
          <div class="wa-detail"><span>Роль</span><strong>${roleBadge(user.admin_role) || "Пользователь"}</strong></div>
          <div class="wa-detail"><span>VPN</span><strong>${user.vpn_online ? "Онлайн" : "Офлайн"}</strong></div>
        </div>
        <div class="wa-form-row">${actions.join("")}</div>
      `);
    } catch (error) {
      toast(error.message, "error");
    }
  }

  async function loadTickets() {
    const target = $("wa-tickets");
    target.innerHTML = '<div class="wa-table-empty">Загрузка...</div>';
    try {
      const data = await api("/tickets", { status: state.tickets.status, limit: 50 });
      const tickets = data.tickets || [];
      if (!tickets.length) {
        target.innerHTML = '<div class="wa-table-empty">Тикетов нет.</div>';
        return;
      }
      target.innerHTML = `
        <table class="wa-table">
          <thead><tr><th>Тема</th><th>Пользователь</th><th>Статус</th><th>Обновлён</th><th></th></tr></thead>
          <tbody>${tickets.map((ticket) => `
            <tr>
              <td><strong>#${esc(ticket.id)} · ${esc(ticket.subject)}</strong><div class="wa-list-meta">${esc(ticket.category_label || "")}</div></td>
              <td>${esc(ticket.first_name || "—")}<div class="wa-list-meta">${ticket.username ? "@" + esc(ticket.username) : esc(ticket.telegram_id)}</div></td>
              <td>${statusBadge(ticket.status)}</td>
              <td>${esc(ticket.updated_at || "—")}</td>
              <td><button class="wa-button wa-button-secondary" data-ticket-open="${esc(ticket.id)}">Открыть</button></td>
            </tr>`).join("")}</tbody>
        </table>`;
    } catch (error) {
      toast(error.message, "error");
      target.innerHTML = `<div class="wa-table-empty">${esc(error.message)}</div>`;
    }
  }

  async function openTicket(ticketId) {
    try {
      const data = await api("/ticket", { ticket_id: Number(ticketId) });
      const ticket = data.ticket || {};
      const messages = data.messages || [];
      openModal(`Тикет #${ticket.id}`, `
        <div class="wa-detail-grid">
          <div class="wa-detail"><span>Тема</span><strong>${esc(ticket.subject || "—")}</strong></div>
          <div class="wa-detail"><span>Пользователь</span><strong>${esc(ticket.first_name || "—")} ${ticket.username ? "@" + esc(ticket.username) : ""}</strong></div>
          <div class="wa-detail"><span>Категория</span><strong>${esc(ticket.category_label || "—")}</strong></div>
          <div class="wa-detail"><span>Статус</span><strong>${statusBadge(ticket.status)}</strong></div>
        </div>
        <div>${messages.map((message) => `
          <div class="wa-message ${message.sender === "admin" ? "is-admin" : ""}">
            <div class="wa-message-meta"><span>${message.sender === "admin" ? "Админ" : "Пользователь"}</span><span>${esc(message.created_at || "")}</span></div>
            ${esc(message.text || "")}
          </div>`).join("")}</div>
        ${ticket.status !== "closed" ? `
          <label class="wa-muted" for="wa-reply">Ответ</label>
          <textarea id="wa-reply" class="wa-textarea" placeholder="Напиши ответ пользователю"></textarea>
          <div class="wa-form-row">
            <button class="wa-button wa-button-primary" data-ticket-action="reply" data-ticket="${esc(ticket.id)}">Отправить ответ</button>
            <button class="wa-button wa-button-danger" data-ticket-action="close" data-ticket="${esc(ticket.id)}">Закрыть тикет</button>
          </div>` : '<div class="wa-note">Тикет закрыт.</div>'}
      `);
    } catch (error) {
      toast(error.message, "error");
    }
  }

  async function loadAdmins() {
    if (!CONFIG.isSuperadmin) return;
    const target = $("wa-admins");
    target.innerHTML = '<div class="wa-table-empty">Загрузка...</div>';
    try {
      const data = await api("/admins");
      const items = data.items || [];
      target.innerHTML = `
        <table class="wa-table">
          <thead><tr><th>Админ</th><th>Роль</th><th>Добавлен</th><th></th></tr></thead>
          <tbody>${items.map((admin) => {
            const protectedAdmin = !!admin.protected;
            const actions = [];
            if (!protectedAdmin) {
              if (admin.role === "superadmin") {
                actions.push(`<button class="wa-button wa-button-secondary" data-admin-action="demote" data-admin="${esc(admin.telegram_id)}">Понизить</button>`);
              } else {
                actions.push(`<button class="wa-button wa-button-secondary" data-admin-action="promote" data-admin="${esc(admin.telegram_id)}">Повысить</button>`);
              }
              actions.push(`<button class="wa-button wa-button-danger" data-admin-action="remove" data-admin="${esc(admin.telegram_id)}">Удалить</button>`);
            }
            return `<tr>
              <td><strong>${esc(admin.first_name || "—")}</strong><div class="wa-list-meta">${admin.username ? "@" + esc(admin.username) + " · " : ""}${esc(admin.telegram_id)}</div></td>
              <td>${roleBadge(admin.role)}${admin.is_active ? "" : ' <span class="wa-badge wa-badge-muted">отключён</span>'}</td>
              <td>${esc(admin.added_at || "—")}</td>
              <td><div class="wa-actions">${actions.join("")}</div></td>
            </tr>`;
          }).join("")}</tbody>
        </table>`;
    } catch (error) {
      toast(error.message, "error");
      target.innerHTML = `<div class="wa-table-empty">${esc(error.message)}</div>`;
    }
  }

  async function loadAudit() {
    if (!CONFIG.isSuperadmin) return;
    const target = $("wa-audit");
    target.innerHTML = '<div class="wa-table-empty">Загрузка...</div>';
    try {
      const data = await api("/audit", { limit: 100 });
      const items = data.items || [];
      if (!items.length) {
        target.innerHTML = '<div class="wa-table-empty">Записей нет.</div>';
        return;
      }
      target.innerHTML = `
        <table class="wa-table">
          <thead><tr><th>Когда</th><th>Админ</th><th>Действие</th><th>Объект</th><th>Детали</th></tr></thead>
          <tbody>${items.map((item) => `
            <tr>
              <td>${esc(item.created_at || "—")}</td>
              <td>${esc(item.admin_first_name || item.admin_username || item.admin_id || "—")}</td>
              <td>${esc(item.action || "—")}</td>
              <td>${esc(item.target_id || "—")}</td>
              <td>${esc(item.meta || "—")}</td>
            </tr>`).join("")}</tbody>
        </table>`;
    } catch (error) {
      toast(error.message, "error");
      target.innerHTML = `<div class="wa-table-empty">${esc(error.message)}</div>`;
    }
  }

  document.querySelectorAll(".wa-nav-item").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.view));
  });

  $("wa-modal-close").addEventListener("click", closeModal);
  $("wa-modal").addEventListener("click", (event) => {
    if (event.target === $("wa-modal")) closeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("wa-modal").hidden) closeModal();
  });

  let userTimer = null;
  $("wa-user-search").addEventListener("input", (event) => {
    clearTimeout(userTimer);
    userTimer = setTimeout(() => {
      state.users.q = event.target.value.trim();
      loadUsers(1);
    }, 300);
  });
  $("wa-user-status").addEventListener("change", (event) => {
    state.users.status = event.target.value;
    loadUsers(1);
  });
  $("wa-user-refresh").addEventListener("click", () => loadUsers(state.users.page));
  $("wa-users-prev").addEventListener("click", () => { if (state.users.page > 1) loadUsers(state.users.page - 1); });
  $("wa-users-next").addEventListener("click", () => { if (state.users.hasMore) loadUsers(state.users.page + 1); });
  $("wa-ticket-status").addEventListener("change", (event) => {
    state.tickets.status = event.target.value;
    loadTickets();
  });
  $("wa-ticket-refresh").addEventListener("click", loadTickets);

  const adminAdd = $("wa-admin-add");
  if (adminAdd) {
    adminAdd.addEventListener("click", async () => {
      const id = Number($("wa-admin-id").value.trim());
      if (!id) { toast("Укажи Telegram ID", "error"); return; }
      try {
        await api("/admins/add", { tg_id: id, role: $("wa-admin-role").value });
        $("wa-admin-id").value = "";
        toast("Админ добавлен");
        loadAdmins();
      } catch (error) { toast(error.message, "error"); }
    });
  }

  document.addEventListener("click", async (event) => {
    const userOpen = event.target.closest("[data-user-open]");
    if (userOpen) { openUser(userOpen.dataset.userOpen); return; }

    const userAction = event.target.closest("[data-user-action]");
    if (userAction) {
      const action = userAction.dataset.userAction;
      const id = Number(userAction.dataset.tg);
      const labels = { approve: "Одобрить заявку?", reject: "Отклонить заявку?", extend: "Продлить на 30 дней?", block: "Заблокировать пользователя?", unblock: "Разблокировать пользователя?", delete: "Удалить пользователя?" };
      if (!confirm(labels[action] || "Выполнить действие?")) return;
      try {
        const payload = { tg_id: id };
        if (action === "extend") payload.days = 30;
        await api("/" + action, payload);
        closeModal();
        toast("Готово");
        loadUsers(state.users.page);
        loadOverview();
      } catch (error) { toast(error.message, "error"); }
      return;
    }

    const ticketOpen = event.target.closest("[data-ticket-open]");
    if (ticketOpen) { openTicket(ticketOpen.dataset.ticketOpen); return; }

    const ticketAction = event.target.closest("[data-ticket-action]");
    if (ticketAction) {
      const action = ticketAction.dataset.ticketAction;
      const ticketId = Number(ticketAction.dataset.ticket);
      try {
        if (action === "reply") {
          const text = ($("wa-reply")?.value || "").trim();
          if (text.length < 2) { toast("Введи ответ", "error"); return; }
          await api("/ticket/reply", { ticket_id: ticketId, text });
          toast("Ответ отправлен");
          openTicket(ticketId);
        } else {
          if (!confirm("Закрыть тикет?")) return;
          await api("/ticket/close", { ticket_id: ticketId });
          closeModal();
          toast("Тикет закрыт");
          loadTickets();
        }
      } catch (error) { toast(error.message, "error"); }
      return;
    }

    const adminAction = event.target.closest("[data-admin-action]");
    if (adminAction) {
      const action = adminAction.dataset.adminAction;
      const id = Number(adminAction.dataset.admin);
      const labels = { promote: "Сделать суперадмином?", demote: "Понизить до админа?", remove: "Отключить администратора?" };
      if (!confirm(labels[action] || "Изменить роль?")) return;
      try {
        if (action === "remove") {
          await api("/admins/remove", { tg_id: id });
        } else {
          await api("/admins/role", { tg_id: id, role: action === "promote" ? "superadmin" : "admin" });
        }
        toast("Роль обновлена");
        loadAdmins();
      } catch (error) { toast(error.message, "error"); }
    }
  });

  showView("overview");
})();
