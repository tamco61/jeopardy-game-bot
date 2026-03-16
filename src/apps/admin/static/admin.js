/* ══════════════════════════════════════════
   НАВИГАЦИЯ
══════════════════════════════════════════ */
const sections = {
    dashboard: "Дашборд",
    rooms: "Комнаты",
    packages: "Пакеты",
};

function switchSection(id) {
    // Активная вкладка в сайдбаре
    document.querySelectorAll(".nav-item").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.section === id);
    });

    // Активная секция
    document.querySelectorAll(".section").forEach(sec => {
        sec.classList.toggle("active", sec.id === id);
    });

    document.getElementById("page-title").textContent = sections[id] || id;

    // Загружаем данные
    if (id === "dashboard") loadDashboard();
    if (id === "rooms")     loadRooms();
    if (id === "packages")  loadPackages();
}

document.querySelectorAll(".nav-item").forEach(btn => {
    btn.addEventListener("click", () => switchSection(btn.dataset.section));
});

document.getElementById("btn-refresh-all").addEventListener("click", () => {
    const activeSection = document.querySelector(".section.active");
    if (activeSection) switchSection(activeSection.id);
});

/* ══════════════════════════════════════════
   TOAST
══════════════════════════════════════════ */
function showToast(message, type = "info", duration = 3500) {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), duration);
}

/* ══════════════════════════════════════════
   МОДАЛЬНОЕ ПОДТВЕРЖДЕНИЕ
══════════════════════════════════════════ */
let modalResolve = null;

function confirm(title, body) {
    return new Promise(resolve => {
        document.getElementById("modal-title").textContent = title;
        document.getElementById("modal-body").textContent = body;
        document.getElementById("modal-backdrop").classList.remove("hidden");
        modalResolve = resolve;
    });
}

document.getElementById("modal-confirm").addEventListener("click", () => {
    document.getElementById("modal-backdrop").classList.add("hidden");
    if (modalResolve) { modalResolve(true); modalResolve = null; }
});

document.getElementById("modal-cancel").addEventListener("click", () => {
    document.getElementById("modal-backdrop").classList.add("hidden");
    if (modalResolve) { modalResolve(false); modalResolve = null; }
});

document.getElementById("modal-backdrop").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) {
        document.getElementById("modal-backdrop").classList.add("hidden");
        if (modalResolve) { modalResolve(false); modalResolve = null; }
    }
});

/* ══════════════════════════════════════════
   HEALTH CHECK / СТАТУС СОЕДИНЕНИЯ
══════════════════════════════════════════ */
async function checkHealth() {
    const dot  = document.getElementById("status-dot");
    const text = document.getElementById("status-text");
    try {
        const res = await fetch("/health");
        if (res.ok) {
            dot.className  = "status-dot online";
            text.textContent = "Сервис онлайн";
        } else {
            throw new Error();
        }
    } catch {
        dot.className  = "status-dot offline";
        text.textContent = "Нет связи";
    }
}

/* ══════════════════════════════════════════
   ДАШБОРД
══════════════════════════════════════════ */
async function loadDashboard() {
    loadStats();
    loadDashboardRooms();
}

async function loadStats() {
    try {
        const res = await fetch("/stats");
        if (!res.ok) throw new Error("HTTP " + res.status);
        const data = await res.json();
        document.getElementById("stat-rooms").textContent    = data.active_rooms;
        document.getElementById("stat-players").textContent  = data.total_players;
        document.getElementById("stat-packages").textContent = data.total_packages;
    } catch (e) {
        console.error("Ошибка загрузки статистики:", e);
    }
}

async function loadDashboardRooms() {
    const tbody = document.getElementById("dashboard-rooms-body");
    try {
        const res = await fetch("/rooms");
        const rooms = await res.json();
        tbody.innerHTML = "";
        if (rooms.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="empty-row">Нет активных комнат</td></tr>`;
            return;
        }
        rooms.forEach(room => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><code>${room.room_id}</code></td>
                <td>${phaseBadge(room.phase)}</td>
                <td>${room.player_count}</td>
                <td>${room.current_round}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch {
        tbody.innerHTML = `<tr><td colspan="4" class="empty-row">Ошибка загрузки</td></tr>`;
    }
}

/* ══════════════════════════════════════════
   КОМНАТЫ
══════════════════════════════════════════ */
async function loadRooms() {
    const tbody = document.getElementById("rooms-body");
    tbody.innerHTML = `<tr><td colspan="6" class="loading-row">Загрузка...</td></tr>`;

    try {
        const res = await fetch("/rooms");
        if (!res.ok) throw new Error("HTTP " + res.status);
        const rooms = await res.json();

        tbody.innerHTML = "";
        if (rooms.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="empty-row">Нет активных комнат</td></tr>`;
            return;
        }

        rooms.forEach(room => {
            const tr = document.createElement("tr");
            const playersHtml = room.players && room.players.length
                ? room.players.map(p => `<span class="player-tag">${escapeHtml(p)}</span>`).join("")
                : '<span style="color:var(--text-muted)">—</span>';

            tr.innerHTML = `
                <td><code>${room.room_id}</code></td>
                <td><small style="color:var(--text-muted)">${room.chat_id}</small></td>
                <td>${phaseBadge(room.phase)}</td>
                <td>${room.current_round}</td>
                <td><div class="players-list">${playersHtml}</div></td>
                <td>
                    <button class="btn-danger" onclick="clearRoom('${room.room_id}')">Сбросить</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch {
        tbody.innerHTML = `<tr><td colspan="6" class="empty-row">Ошибка загрузки</td></tr>`;
    }
}

async function clearRoom(roomId) {
    const ok = await confirm(
        "Сбросить комнату?",
        `Все данные комнаты ${roomId} будут удалены из Redis. Текущая игровая сессия завершится.`
    );
    if (!ok) return;

    try {
        const res = await fetch(`/rooms/clear/${roomId}`, { method: "POST" });
        if (res.ok) {
            showToast(`Комната ${roomId} успешно удалена`, "success");
            loadRooms();
            loadStats();
        } else {
            showToast("Ошибка при удалении комнаты", "error");
        }
    } catch {
        showToast("Ошибка сети", "error");
    }
}

/* ══════════════════════════════════════════
   ПАКЕТЫ
══════════════════════════════════════════ */
async function loadPackages() {
    const tbody = document.getElementById("packages-body");
    tbody.innerHTML = `<tr><td colspan="3" class="loading-row">Загрузка...</td></tr>`;

    try {
        const res = await fetch("/packages");
        if (!res.ok) throw new Error("HTTP " + res.status);
        const packs = await res.json();

        tbody.innerHTML = "";
        if (packs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="3" class="empty-row">Пакеты не найдены. Загрузите .siq через Telegram-бот.</td></tr>`;
            return;
        }

        packs.forEach(pack => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><code>${pack.id}</code></td>
                <td><strong>${escapeHtml(pack.title)}</strong></td>
                <td>
                    <button class="btn-danger" onclick="deletePackage(${pack.id}, '${escapeHtml(pack.title).replace(/'/g, "\\'")}')">Удалить</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch {
        tbody.innerHTML = `<tr><td colspan="3" class="empty-row">Ошибка загрузки</td></tr>`;
    }
}

async function deletePackage(id, title) {
    const ok = await confirm(
        "Удалить пакет?",
        `Пакет «${title}» и все его вопросы будут удалены безвозвратно.`
    );
    if (!ok) return;

    try {
        const res = await fetch(`/packages/${id}`, { method: "DELETE" });
        if (res.ok) {
            showToast(`Пакет «${title}» удалён`, "success");
            loadPackages();
            loadStats();
        } else if (res.status === 404) {
            showToast("Пакет не найден", "error");
        } else {
            showToast("Ошибка при удалении", "error");
        }
    } catch {
        showToast("Ошибка сети", "error");
    }
}

/* ══════════════════════════════════════════
   ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
══════════════════════════════════════════ */
function phaseBadge(phase) {
    const label = {
        LOBBY:            "Лобби",
        BOARD_VIEW:       "Табло",
        READING:          "Вопрос",
        SPECIAL_EVENT:    "Спец. событие",
        WAITING_FOR_PUSH: "Ждём нажатия",
        ANSWERING:        "Ответ",
        FINAL_ROUND:      "Финальный раунд",
        FINAL_STAKE:      "Ставка",
        FINAL_ANSWER:     "Финальный ответ",
        RESULTS:          "Результаты",
        PAUSE:            "Пауза",
    }[phase] || phase;

    return `<span class="phase-badge phase-${phase}">${label}</span>`;
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

/* ══════════════════════════════════════════
   ИНИЦИАЛИЗАЦИЯ
══════════════════════════════════════════ */
// Загружаем начальный раздел
switchSection("dashboard");

// Health check каждые 10 секунд
checkHealth();
setInterval(checkHealth, 10000);

// Автообновление статистики каждые 15 секунд
setInterval(() => {
    const active = document.querySelector(".section.active");
    if (!active) return;
    if (active.id === "dashboard") loadDashboard();
    if (active.id === "rooms")     loadRooms();
}, 15000);
