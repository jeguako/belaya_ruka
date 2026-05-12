(async function () {
  "use strict";

  /* ── Telegram WebApp init ─────────────────────────────── */
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      if (typeof tg.requestFullscreen === "function") tg.requestFullscreen();
      if (typeof tg.disableVerticalSwipes === "function") tg.disableVerticalSwipes();
      if (typeof tg.enableClosingConfirmation === "function") tg.enableClosingConfirmation();
    } catch (_) {}
  }

  function applyTelegramChrome() {
    const root = document.documentElement;
    if (tg && typeof tg.colorScheme === "string") {
      root.dataset.tgScheme = tg.colorScheme;
    } else {
      root.dataset.tgScheme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    if (tg && tg.themeParams) {
      const p = tg.themeParams;
      const bg = p.bg_color;
      const hdr = p.secondary_bg_color || bg;
      try {
        if (typeof tg.setBackgroundColor === "function" && bg) tg.setBackgroundColor(bg);
        if (typeof tg.setHeaderColor === "function" && hdr) tg.setHeaderColor(hdr);
      } catch (_) {}
    }
  }
  applyTelegramChrome();
  if (tg && typeof tg.onEvent === "function") {
    tg.onEvent("themeChanged", applyTelegramChrome);
  } else {
    try {
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTelegramChrome);
    } catch (_) {}
  }

  /* prevent double-tap zoom on all elements */
  let lastTap = 0;
  document.addEventListener("touchend", function (e) {
    const now = Date.now();
    if (now - lastTap < 300) e.preventDefault();
    lastTap = now;
  }, { passive: false });

  /* ── State ────────────────────────────────────────────── */
  const STORAGE_KEY = "belaya_ruka_v9";
  const GIFT_BOTTLES = 50;

  const state = loadState();
  state.profile   = state.profile   || {};
  state.addresses = Array.isArray(state.addresses) ? state.addresses : [];
  state.products  = Array.isArray(state.products)  ? state.products  : [];
  state.b2bSent   = state.b2bSent   || false;

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : {};
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (_) { return {}; }
  }

  function saveState() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch (_) {}
  }

  function syncCatalogToBot() {
    sendToBot({ event: "catalog_sync", products: state.products });
  }

  async function hydrateCatalogFromServer() {
    try {
      const url = new URL("catalog.json", window.location.href);
      url.searchParams.set("t", String(Date.now()));
      const r = await fetch(url.href, { cache: "no-store" });
      if (!r.ok) return;
      const data = await r.json();
      if (!Array.isArray(data)) return;
      state.products = data;
      saveState();
    } catch (_) {}
  }

  /* Merge profile from bot (#u=…&tab=…) — после объявления saveState */
  let initialTab = "home";
  try {
    const hash = window.location.hash.replace(/^#/, "");
    const params = new URLSearchParams(hash);
    const tabParam = params.get("tab");
    if (tabParam === "b2b") initialTab = "b2b";
    else if (tabParam === "profile") initialTab = "profile";

    const enc = params.get("u");
    if (enc) {
      const padded = enc.replace(/-/g, "+").replace(/_/g, "/");
      const pad = padded.length % 4 === 0 ? "" : "====".slice(padded.length % 4);
      const decoded = atob(padded + pad);
      const botProfile = JSON.parse(decoded);
      const assign = (bk, sk) => {
        const v = botProfile[bk];
        if (v !== undefined && v !== null && String(v).trim() !== "") state.profile[sk] = String(v).trim();
      };
      assign("name", "name");
      assign("phone", "phone");
      assign("mainAddress", "mainAddress");
      assign("floor", "floor");
      assign("intercom", "intercom");
      assign("notes", "notes");
      if (typeof botProfile.litersTotal === "number") {
        state.litersTotal = botProfile.litersTotal;
        state.bottlesTotal = Math.floor(botProfile.litersTotal / 19);
      }
      saveState();
    }
  } catch (_) {}

  function escHtml(v) {
    return String(v || "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }

  function pluralize(n, forms) {
    const v = Math.abs(n) % 100, v1 = v % 10;
    if (v > 10 && v < 20) return forms[2];
    if (v1 > 1 && v1 < 5) return forms[1];
    if (v1 === 1) return forms[0];
    return forms[2];
  }

  function sendToBot(payload) {
    if (!tg || typeof tg.sendData !== "function") return;
    try { tg.sendData(JSON.stringify(payload)); } catch (_) {}
  }

  function haptic(type) {
    try {
      if (tg && tg.HapticFeedback && typeof tg.HapticFeedback.notificationOccurred === "function") {
        tg.HapticFeedback.notificationOccurred(type);
      }
    } catch (_) {}
  }

  /* ── Tab switching ────────────────────────────────────── */
  const tabs      = Array.from(document.querySelectorAll(".tab"));
  const navBtns   = Array.from(document.querySelectorAll(".bottom-nav [data-tab]"));

  function activateTab(name) {
    tabs.forEach(el => el.classList.toggle("active", el.id === `tab-${name}`));
    navBtns.forEach(btn => btn.classList.toggle("active", btn.dataset.tab === name));
    if (name === "profile") renderProfile();
    if (name === "home")    renderCatalog();
    if (name === "b2b")     renderB2B();
  }

  navBtns.forEach(btn => btn.addEventListener("click", () => activateTab(btn.dataset.tab || "home")));

  /* ── Catalog ──────────────────────────────────────────── */
  const catalogEl      = document.getElementById("catalog");
  const catalogEmptyEl = document.getElementById("catalog-empty");
  const catalogCountEl = document.getElementById("catalog-count");

  function renderCatalog() {
    const products = state.products || [];
    catalogCountEl.textContent = `${products.length} ${pluralize(products.length, ["товар","товара","товаров"])}`;
    if (products.length === 0) {
      catalogEl.innerHTML = "";
      catalogEmptyEl.style.display = "";
      return;
    }
    catalogEmptyEl.style.display = "none";
    catalogEl.innerHTML = products.map((p, idx) => {
      const img = p.photo ? `style="background-image:url('${escHtml(p.photo)}')"` : "";
      const minV = p.minVolume ? `<div class="min-vol">от ${escHtml(p.minVolume)} шт</div>` : "";
      const desc = p.description
        ? `<div class="product-desc muted">${escHtml(p.description)}</div>`
        : "";
      return `
        <article class="product" data-idx="${idx}">
          <div class="img" ${img}></div>
          <div class="body">
            <div class="title">${escHtml(p.title || "Без названия")}</div>
            ${desc}
            <div class="price">${escHtml(p.price || "0")} ₽</div>
            ${minV}
            <button class="order-btn" data-idx="${idx}">Заказать</button>
          </div>
        </article>`;
    }).join("");
  }

  catalogEl.addEventListener("click", e => {
    const btn = e.target.closest(".order-btn");
    if (!btn) return;
    const idx = Number(btn.dataset.idx);
    const p = (state.products || [])[idx];
    if (p) openOrderFor(p);
  });

  /* ── Admin product list ───────────────────────────────── */
  const adminProductList = document.getElementById("admin-product-list");

  function renderAdminList() {
    const products = state.products || [];
    if (products.length === 0) {
      adminProductList.innerHTML = `<div class="muted small" style="margin-bottom:10px">Товаров нет.</div>`;
      return;
    }
    adminProductList.innerHTML = products.map((p, idx) => {
      const img = p.photo ? `style="background-image:url('${escHtml(p.photo)}')"` : "";
      return `
        <div class="admin-product-item">
          <div class="admin-product-img" ${img}></div>
          <div class="admin-product-meta">
            <div class="admin-product-name">${escHtml(p.title)}</div>
            <div class="admin-product-price">${escHtml(p.price)} ₽ · от ${escHtml(p.minVolume || "1")} шт</div>
          </div>
          <div class="admin-product-actions">
            <button class="mini-btn" data-admin-edit="${idx}">✏️</button>
            <button class="mini-btn danger" data-admin-del="${idx}">🗑</button>
          </div>
        </div>`;
    }).join("");
  }

  adminProductList.addEventListener("click", e => {
    const delBtn  = e.target.closest("[data-admin-del]");
    const editBtn = e.target.closest("[data-admin-edit]");
    if (delBtn) {
      const idx = Number(delBtn.dataset.adminDel);
      if (confirm(`Удалить «${(state.products[idx] || {}).title}»?`)) {
        state.products.splice(idx, 1);
        saveState();
        syncCatalogToBot();
        renderAdminList();
        renderCatalog();
      }
    }
    if (editBtn) {
      const idx = Number(editBtn.dataset.adminEdit);
      const p = state.products[idx];
      if (!p) return;
      document.getElementById("admin-title").value       = p.title        || "";
      document.getElementById("admin-photo").value       = p.photo        || "";
      document.getElementById("admin-description").value = p.description  || "";
      document.getElementById("admin-price").value       = p.price        || "";
      document.getElementById("admin-min-volume").value  = p.minVolume    || "3";
      document.getElementById("admin-size").value        = p.size         || "";
      /* store editing index */
      document.getElementById("save-product").dataset.editIdx = String(idx);
      /* open details */
      document.querySelector(".admin-add-details").setAttribute("open", "");
    }
  });

  /* ── Admin add/edit form ──────────────────────────────── */
  const saveProductBtn = document.getElementById("save-product");

  function readImageAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload  = () => resolve(String(r.result || ""));
      r.onerror = reject;
      r.readAsDataURL(file);
    });
  }

  saveProductBtn.addEventListener("click", async () => {
    const title = document.getElementById("admin-title").value.trim();
    const price = document.getElementById("admin-price").value.trim();
    if (!title || !price) { alert("Укажите название и цену."); return; }

    let photo = document.getElementById("admin-photo").value.trim();
    const photoFile = document.getElementById("admin-photo-file");
    if (!photo && photoFile.files && photoFile.files[0]) {
      try { photo = await readImageAsDataUrl(photoFile.files[0]); } catch (_) { photo = ""; }
    }

    const product = {
      id: String(Date.now()),
      title,
      photo,
      description: document.getElementById("admin-description").value.trim(),
      price,
      minVolume: document.getElementById("admin-min-volume").value.trim() || "3",
      size: document.getElementById("admin-size").value.trim(),
    };

    const rawEditIdx = saveProductBtn.dataset.editIdx;
    const editIdx =
      rawEditIdx === undefined || rawEditIdx === "" ? -1 : Number(rawEditIdx);
    if (editIdx >= 0 && editIdx < state.products.length) {
      product.id = state.products[editIdx].id;
      state.products[editIdx] = product;
      delete saveProductBtn.dataset.editIdx;
    } else {
      state.products.push(product);
    }

    saveState();
    syncCatalogToBot();

    ["admin-title","admin-photo","admin-description","admin-price","admin-size"].forEach(id => {
      document.getElementById(id).value = "";
    });
    document.getElementById("admin-min-volume").value = "3";
    document.getElementById("admin-photo-file").value = "";

    document.querySelector(".admin-add-details").removeAttribute("open");
    renderAdminList();
    renderCatalog();
    haptic("success");
  });

  /* ── Profile ──────────────────────────────────────────── */
  const litersTotalEl  = document.getElementById("liters-total");
  const litersLeftEl   = document.getElementById("liters-left");
  const progressFillEl = document.getElementById("progress-fill");

  function renderProfile() {
    const p = state.profile;
    /* fill view rows */
    document.getElementById("view-name").textContent          = p.name         || "—";
    document.getElementById("view-phone").textContent         = p.phone        || "—";
    document.getElementById("view-address").textContent       = p.mainAddress  || "—";
    const fi = [p.floor, p.intercom].filter(Boolean).join(" / ");
    document.getElementById("view-floor-intercom").textContent = fi || "—";
    document.getElementById("view-notes").textContent         = p.notes        || "—";

    /* fill form fields too (so edit opens pre-filled) */
    document.getElementById("profile-name").value         = p.name        || "";
    document.getElementById("profile-phone").value        = p.phone       || "";
    document.getElementById("profile-main-address").value = p.mainAddress || "";
    document.getElementById("profile-floor").value        = p.floor       || "";
    document.getElementById("profile-intercom").value     = p.intercom    || "";
    document.getElementById("profile-notes").value        = p.notes       || "";

    /* progress */
    const bottles = Number(state.bottlesTotal || 0);
    const cycle   = bottles % GIFT_BOTTLES;
    const left    = bottles > 0 ? GIFT_BOTTLES - cycle : GIFT_BOTTLES;
    const pct     = (cycle / GIFT_BOTTLES) * 100;
    litersTotalEl.textContent  = `${bottles} бут.`;
    litersLeftEl.textContent   = `${left} бут.`;
    progressFillEl.style.width = `${Math.min(pct, 100)}%`;

    renderAddresses();
    renderAdminList();
  }

  /* edit toggle */
  const profileView   = document.getElementById("profile-view");
  const profileForm   = document.getElementById("profile-form");
  const editToggleBtn = document.getElementById("edit-profile-toggle");
  const cancelProfileBtn = document.getElementById("cancel-profile");
  const saveProfileBtn   = document.getElementById("save-profile");

  editToggleBtn.addEventListener("click", () => {
    profileView.classList.add("hidden");
    profileForm.classList.remove("hidden");
    editToggleBtn.textContent = "";
  });
  cancelProfileBtn.addEventListener("click", () => {
    profileForm.classList.add("hidden");
    profileView.classList.remove("hidden");
    editToggleBtn.textContent = "Изменить";
  });
  saveProfileBtn.addEventListener("click", () => {
    state.profile = {
      name:        document.getElementById("profile-name").value.trim(),
      phone:       document.getElementById("profile-phone").value.trim(),
      mainAddress: document.getElementById("profile-main-address").value.trim(),
      floor:       document.getElementById("profile-floor").value.trim(),
      intercom:    document.getElementById("profile-intercom").value.trim(),
      notes:       document.getElementById("profile-notes").value.trim(),
    };
    saveState();
    sendToBot({ event: "profile_update", ...state.profile });
    profileForm.classList.add("hidden");
    profileView.classList.remove("hidden");
    editToggleBtn.textContent = "Изменить";
    renderProfile();
    haptic("success");
  });

  /* ── Addresses ────────────────────────────────────────── */
  const addressListEl  = document.getElementById("address-list");
  const addressLabelEl = document.getElementById("address-label");
  const addressValueEl = document.getElementById("address-value");

  function renderAddresses() {
    const list = state.addresses || [];
    if (list.length === 0) {
      addressListEl.innerHTML = `<div class="muted small">Дополнительных адресов нет.</div>`;
      return;
    }
    addressListEl.innerHTML = list.map(a => `
      <div class="address-item">
        <div class="address-meta">
          <div style="font-weight:600;font-size:13px">${escHtml(a.label || "Адрес")}</div>
          <div class="muted">${escHtml(a.address)}</div>
        </div>
        <div class="address-actions">
          <button class="mini-btn danger" data-del-addr="${escHtml(a.id)}">Удалить</button>
        </div>
      </div>`).join("");
  }

  addressListEl.addEventListener("click", e => {
    const btn = e.target.closest("[data-del-addr]");
    if (!btn) return;
    state.addresses = state.addresses.filter(a => a.id !== btn.dataset.delAddr);
    saveState();
    renderAddresses();
  });

  document.getElementById("add-address").addEventListener("click", () => {
    const label   = addressLabelEl.value.trim();
    const address = addressValueEl.value.trim();
    if (!address) { alert("Введите адрес."); return; }
    state.addresses.push({ id: String(Date.now()), label: label || "Адрес", address });
    saveState();
    addressLabelEl.value = "";
    addressValueEl.value = "";
    renderAddresses();
  });

  /* ── B2B ──────────────────────────────────────────────── */
  const b2bFormWrap = document.getElementById("b2b-form-wrap");
  const b2bSuccess  = document.getElementById("b2b-success");
  const sendB2bBtn  = document.getElementById("send-b2b");
  const b2bAgainBtn = document.getElementById("b2b-again");

  function renderB2B() {
    if (state.b2bSent) {
      b2bFormWrap.classList.add("hidden");
      b2bSuccess.classList.remove("hidden");
    } else {
      b2bFormWrap.classList.remove("hidden");
      b2bSuccess.classList.add("hidden");
    }
  }

  sendB2bBtn.addEventListener("click", () => {
    const company = document.getElementById("b2b-company").value.trim();
    const contact = document.getElementById("b2b-contact").value.trim();
    if (!company || !contact) { alert("Заполните название компании и контакт для связи."); return; }
    sendToBot({
      event:          "b2b",
      company,
      inn:            document.getElementById("b2b-inn").value.trim(),
      pointsCount:    document.getElementById("b2b-points-count").value.trim(),
      pointsAddresses:document.getElementById("b2b-points-addresses").value.trim(),
      volume:         document.getElementById("b2b-volume").value.trim(),
      comment:        document.getElementById("b2b-comment").value.trim(),
      contact,
    });
    state.b2bSent = true;
    saveState();
    renderB2B();
    haptic("success");
  });

  b2bAgainBtn.addEventListener("click", () => {
    state.b2bSent = false;
    saveState();
    /* clear fields */
    ["b2b-company","b2b-inn","b2b-points-count","b2b-points-addresses","b2b-volume","b2b-comment","b2b-contact"]
      .forEach(id => { document.getElementById(id).value = ""; });
    renderB2B();
  });

  /* ── Order modal + calendar ───────────────────────────── */
  const orderModal   = document.getElementById("order-modal");
  const modalTitle   = document.getElementById("modal-title");
  const qtyValueEl   = document.getElementById("qty-value");
  const calGridEl    = document.getElementById("cal-grid");
  const calPrevBtn   = document.getElementById("cal-prev");
  const calNextBtn   = document.getElementById("cal-next");
  const calMonthLabel = document.getElementById("cal-month-label");
  const timeSlotsEl  = document.getElementById("time-slots");
  const timeCustomEl = document.getElementById("order-time-custom");
  const orderComment = document.getElementById("order-comment");
  const modalSubmit  = document.getElementById("modal-submit");

  const RU_MONTHS = [
    "Январь","Февраль","Март","Апрель","Май","Июнь",
    "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь",
  ];

  let activeProduct = null;
  let quantity      = 3;
  let selectedDate  = "";
  let selectedTime  = "";
  let calViewYear   = new Date().getFullYear();
  let calViewMonth  = new Date().getMonth(); /* 0–11 */

  function pad2(n) { return String(n).padStart(2, "0"); }

  function shiftCalMonth(delta) {
    calViewMonth += delta;
    while (calViewMonth > 11) { calViewMonth -= 12; calViewYear += 1; }
    while (calViewMonth < 0) { calViewMonth += 12; calViewYear -= 1; }
    renderCalendar();
  }

  function renderCalendar() {
    calMonthLabel.textContent = `${RU_MONTHS[calViewMonth]} ${calViewYear}`;
    calGridEl.innerHTML = "";

    const first = new Date(calViewYear, calViewMonth, 1);
    const lastDay = new Date(calViewYear, calViewMonth + 1, 0).getDate();
    /* Monday-first offset */
    let start = first.getDay() - 1;
    if (start < 0) start = 6;

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    for (let i = 0; i < start; i++) {
      const pad = document.createElement("div");
      pad.className = "cal-cell cal-cell-empty";
      calGridEl.appendChild(pad);
    }

    for (let d = 1; d <= lastDay; d++) {
      const cell = document.createElement("button");
      cell.type = "button";
      cell.className = "cal-cell cal-day";
      const dt = new Date(calViewYear, calViewMonth, d);
      dt.setHours(0, 0, 0, 0);
      const ds = `${pad2(d)}.${pad2(calViewMonth + 1)}.${calViewYear}`;
      const isPast = dt < today;
      const isSel = ds === selectedDate;

      if (isPast) {
        cell.classList.add("cal-past");
        cell.disabled = true;
        cell.textContent = "·";
      } else {
        cell.textContent = isSel ? `✓${d}` : String(d);
        if (isSel) cell.classList.add("cal-selected");
        cell.addEventListener("click", () => {
          selectedDate = ds;
          renderCalendar();
          timeSlotsEl.querySelectorAll(".time-slot").forEach(s => s.classList.remove("selected"));
          selectedTime = "";
          timeCustomEl.value = "";
        });
      }
      calGridEl.appendChild(cell);
    }
  }

  calPrevBtn.addEventListener("click", () => shiftCalMonth(-1));
  calNextBtn.addEventListener("click", () => shiftCalMonth(1));

  timeSlotsEl.addEventListener("click", e => {
    const slot = e.target.closest(".time-slot");
    if (!slot) return;
    selectedTime = slot.dataset.time;
    timeSlotsEl.querySelectorAll(".time-slot").forEach(s => s.classList.toggle("selected", s === slot));
    timeCustomEl.value = "";
  });

  timeCustomEl.addEventListener("input", () => {
    selectedTime = timeCustomEl.value.trim();
    timeSlotsEl.querySelectorAll(".time-slot").forEach(s => s.classList.remove("selected"));
  });

  function setQuantity(next, min) {
    const limit = Math.max(1, Number(min || 3));
    quantity = Math.max(limit, Number(next || limit));
    qtyValueEl.textContent = String(quantity);
  }

  document.getElementById("qty-minus").addEventListener("click", () => {
    const minV = activeProduct && activeProduct.minVolume;
    setQuantity(quantity - 1, minV || 3);
  });
  document.getElementById("qty-plus").addEventListener("click", () => {
    const minV = activeProduct && activeProduct.minVolume;
    setQuantity(quantity + 1, minV || 3);
  });

  function openOrderFor(product) {
    activeProduct  = product;
    selectedDate   = "";
    selectedTime   = "";
    const now = new Date();
    calViewYear  = now.getFullYear();
    calViewMonth = now.getMonth();
    modalTitle.textContent = `Заказ: ${product.title}`;
    setQuantity(Number(product.minVolume || 3), Number(product.minVolume || 3));
    orderComment.value  = "";
    timeCustomEl.value  = "";
    timeSlotsEl.querySelectorAll(".time-slot").forEach(s => s.classList.remove("selected"));
    renderCalendar();
    orderModal.classList.remove("hidden");
  }

  function closeOrder() {
    orderModal.classList.add("hidden");
    activeProduct = null;
  }

  document.getElementById("modal-close").addEventListener("click", closeOrder);
  orderModal.addEventListener("click", e => {
    if (e.target === orderModal || e.target.classList.contains("modal-backdrop")) closeOrder();
  });

  modalSubmit.addEventListener("click", () => {
    if (!activeProduct) return;
    const mainAddr = state.profile.mainAddress || "";
    if (!mainAddr) {
      alert("Укажите адрес доставки в разделе «Профиль».");
      closeOrder();
      activateTab("profile");
      return;
    }
    if (!selectedDate) { alert("Выберите дату в календаре."); return; }
    const time = selectedTime || timeCustomEl.value.trim() || "не указано";

    sendToBot({
      event:           "order",
      productTitle:    activeProduct.title,
      quantity,
      comment:         orderComment.value.trim(),
      date:            selectedDate,
      time,
      selectedAddress: mainAddr,
    });

    state.bottlesTotal = Number(state.bottlesTotal || 0) + quantity;
    state.litersTotal  = Number(state.litersTotal  || 0) + quantity * 19;
    saveState();
    closeOrder();
    haptic("success");
    alert(`Заказ на ${quantity} бут. принят.\nДата: ${selectedDate}\nИнтервал: ${time}`);
  });

  /* ── Initial render ───────────────────────────────────── */
  await hydrateCatalogFromServer();
  renderCatalog();
  renderProfile();
  renderB2B();
  activateTab(initialTab);

})();
