/* ══════════════════════════════════════════
   СОСТОЯНИЕ
══════════════════════════════════════════ */
let socket = null;
let currentRoomId = null;
let playerName = "";
let gameFinished = false;
let gameState = {
    phase: "LOBBY",
    board: [],
    closedQuestions: [],
    scores: {}
};

/* ══════════════════════════════════════════
   DOM-ЭЛЕМЕНТЫ
══════════════════════════════════════════ */
const joinScreen            = document.getElementById("join-screen");
const gameScreen            = document.getElementById("game-screen");
const lobbyList             = document.getElementById("lobby-list");
const btnJoin               = document.getElementById("btn-join");
const btnRefresh            = document.getElementById("btn-refresh");
const playerNameInput       = document.getElementById("player-name");
const roomDisplay           = document.getElementById("room-display");
const roundDisplay          = document.getElementById("round-display");
const scoreboard            = document.getElementById("scoreboard");
const lobbyView             = document.getElementById("lobby-view");
const playerList            = document.getElementById("player-list");
const btnReady              = document.getElementById("btn-ready");
const btnNotReady           = document.getElementById("btn-notready");
const btnLeave              = document.getElementById("btn-leave");
const gameContainer         = document.getElementById("game-container");
const boardView             = document.getElementById("board-view");
const questionView          = document.getElementById("question-view");
const qText                 = document.getElementById("q-text");
const qValue                = document.getElementById("q-value");
const buzzerArea            = document.getElementById("buzzer-area");
const btnBuzzer             = document.getElementById("btn-buzzer");
const answeringStatus       = document.getElementById("answering-status");
const answeringName         = document.getElementById("answering-name");
const answerInputContainer  = document.getElementById("answer-input-container");
const answerInput           = document.getElementById("answer-input");
const btnSubmitAnswer       = document.getElementById("btn-submit-answer");
const answerStatus          = document.getElementById("answer-status");
const resultsView           = document.getElementById("results-view");
const resultsList           = document.getElementById("results-list");
const btnPlayAgain          = document.getElementById("btn-play-again");
const toastContainer        = document.getElementById("toast-container");

/* ══════════════════════════════════════════
   TOAST-УВЕДОМЛЕНИЯ
══════════════════════════════════════════ */
function showToast(message, type = "info", duration = 3000) {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), duration);
}

/* ══════════════════════════════════════════
   ПЕРЕКЛЮЧЕНИЕ ФАЗЫ
══════════════════════════════════════════ */
function setGamePhase(phase) {
    gameState.phase = phase;
    if (phase === "LOBBY") {
        lobbyView.classList.remove("hidden");
        gameContainer.classList.add("hidden");
    } else {
        lobbyView.classList.add("hidden");
        gameContainer.classList.remove("hidden");
    }
}

/* ══════════════════════════════════════════
   ЛОББИ: ЗАГРУЗКА СПИСКА КОМНАТ
══════════════════════════════════════════ */
async function fetchLobbies() {
    lobbyList.innerHTML = `
        <div class="loader-row">
            <div class="spinner"></div>
            <span>Поиск игр...</span>
        </div>`;

    try {
        const res = await fetch("/rooms");
        if (!res.ok) throw new Error("HTTP " + res.status);
        const rooms = await res.json();

        lobbyList.innerHTML = "";
        if (rooms.length === 0) {
            lobbyList.innerHTML = `<div class="empty-row">Нет активных лобби. Создайте игру в Telegram!</div>`;
            return;
        }

        rooms.forEach(room => {
            const item = document.createElement("div");
            item.className = "lobby-item";
            const phase = room.phase || "—";
            item.innerHTML = `
                <span class="lobby-room-id">${room.room_id}</span>
                <span class="lobby-meta">👥 ${room.player_count} · ${phase}</span>
            `;
            item.addEventListener("click", () => selectLobby(room.room_id, item));
            lobbyList.appendChild(item);
        });
    } catch (e) {
        lobbyList.innerHTML = `<div class="empty-row" style="color:var(--danger)">Ошибка загрузки списка комнат</div>`;
    }
}

function selectLobby(roomId, element) {
    currentRoomId = roomId;
    document.querySelectorAll(".lobby-item").forEach(el => el.classList.remove("selected"));
    element.classList.add("selected");
    validateJoin();
}

function validateJoin() {
    playerName = playerNameInput.value.trim();
    btnJoin.disabled = !(currentRoomId && playerName.length > 0);
}

playerNameInput.addEventListener("input", validateJoin);
btnRefresh.addEventListener("click", fetchLobbies);

btnJoin.addEventListener("click", () => {
    if (currentRoomId && playerName) {
        connectToGame(currentRoomId, playerName);
    }
});

/* ══════════════════════════════════════════
   WEBSOCKET — ПОДКЛЮЧЕНИЕ К ИГРЕ
══════════════════════════════════════════ */
function connectToGame(roomId, name) {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${location.host}/ws/${roomId}/${encodeURIComponent(name)}`;

    socket = new WebSocket(url);

    socket.addEventListener("open", () => {
        joinScreen.classList.add("hidden");
        gameScreen.classList.remove("hidden");
        roomDisplay.textContent = `Room: ${roomId}`;
        showToast("Подключено к игре!", "success");
    });

    socket.addEventListener("message", ({ data }) => {
        try {
            handleServerMessage(JSON.parse(data));
        } catch (e) {
            console.error("Ошибка разбора сообщения:", e);
        }
    });

    socket.addEventListener("close", () => {
        if (gameFinished) return; // Результаты уже показаны — не перезагружаем
        showToast("Соединение потеряно. Страница перезагрузится...", "error", 3000);
        setTimeout(() => location.reload(), 3000);
    });

    socket.addEventListener("error", () => {
        showToast("Ошибка WebSocket-соединения", "error");
    });
}

function sendEvent(obj) {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(obj));
        return true;
    }
    return false;
}

/* ══════════════════════════════════════════
   ОБРАБОТКА СОБЫТИЙ ОТ СЕРВЕРА
══════════════════════════════════════════ */
function handleServerMessage({ event_type, payload }) {
    switch (event_type) {
        case "lobby_updated":
            renderLobbyUpdate(payload);
            break;
        case "board_updated":
            renderBoardUpdate(payload);
            break;
        case "question_opened":
            showQuestion(payload);
            break;
        case "buzzer_activated":
            activateBuzzer();
            break;
        case "answering_started":
            showAnsweringState(payload);
            break;
        case "verdict_announced":
            showVerdict(payload);
            break;
        case "game_finished":
            showResults(payload);
            break;
        default:
            console.log("Неизвестное событие:", event_type, payload);
    }
}

/* ══════════════════════════════════════════
   ЛОББИ (ВНУТРИ ИГРЫ)
══════════════════════════════════════════ */
function renderLobbyUpdate({ players }) {
    setGamePhase("LOBBY");
    playerList.innerHTML = "";

    players.forEach(p => {
        const item = document.createElement("div");
        item.className = "player-item";
        const isMe = p.id === playerName;
        item.innerHTML = `
            <span class="player-name">${p.name}${isMe ? " (вы)" : ""}</span>
            <span class="status-badge ${p.is_ready ? "ready" : "waiting"}">
                ${p.is_ready ? "Готов" : "Ожидание"}
            </span>`;
        playerList.appendChild(item);

        if (isMe) {
            btnReady.classList.toggle("hidden", p.is_ready);
            btnNotReady.classList.toggle("hidden", !p.is_ready);
        }
    });

    updateScoreboard(
        Object.fromEntries(players.map(p => [p.id, { name: p.name, score: p.score || 0 }]))
    );
}

/* ══════════════════════════════════════════
   ТАБЛО (ДОСКА ВОПРОСОВ)
══════════════════════════════════════════ */
function renderBoardUpdate({ board, closed_questions, scores, round_name, round_number }) {
    setGamePhase("GAME");
    gameState.board = board;
    gameState.closedQuestions = closed_questions || [];

    roundDisplay.textContent = round_name ? `${round_name} (${round_number})` : `Раунд ${round_number}`;
    updateScoreboard(scores);
    renderBoard();
    questionView.classList.add("hidden");
    resultsView.classList.add("hidden");
}

function renderBoard() {
    boardView.innerHTML = "";
    if (!gameState.board || gameState.board.length === 0) return;

    gameState.board.forEach(theme => {
        const row = document.createElement("div");
        row.className = "board-row";

        // Название темы
        const themeCell = document.createElement("div");
        themeCell.className = "cell theme-cell";
        themeCell.textContent = theme.theme;
        row.appendChild(themeCell);

        // Вопросы
        theme.questions.forEach(q => {
            const cell = document.createElement("div");
            const isClosed = gameState.closedQuestions.includes(q.id);
            cell.className = "cell" + (isClosed ? " closed" : " q-cell");
            cell.textContent = isClosed ? "✕" : q.value;
            if (!isClosed) {
                cell.addEventListener("click", () => selectQuestion(q.id));
            }
            row.appendChild(cell);
        });

        boardView.appendChild(row);
    });
}

/* ══════════════════════════════════════════
   ВОПРОС
══════════════════════════════════════════ */
function showQuestion({ text, value }) {
    qText.textContent = text;
    qValue.textContent = `${value} очков`;

    // Сброс состояния
    setBuzzerState("disabled");
    answeringStatus.classList.add("hidden");
    answerInputContainer.classList.add("hidden");
    answerStatus.classList.add("hidden");
    answerInput.value = "";

    questionView.classList.remove("hidden");
}

function activateBuzzer() {
    // Показываем question-view если он был скрыт (например после неверного ответа)
    questionView.classList.remove("hidden");
    // Сбрасываем состояние предыдущего ответа
    answerInputContainer.classList.add("hidden");
    answerStatus.classList.add("hidden");
    answeringStatus.classList.add("hidden");
    answerInput.value = "";
    setBuzzerState("active");
}

function showAnsweringState({ player_id, name }) {
    setBuzzerState("disabled");

    if (player_id === playerName) {
        // Это мы отвечаем
        answerInputContainer.classList.remove("hidden");
        answeringStatus.classList.add("hidden");
        answerStatus.classList.add("hidden");
        answerInput.focus();
        showToast("Ваша очередь отвечать!", "success");
    } else {
        // Другой игрок
        answerInputContainer.classList.add("hidden");
        answeringName.textContent = `${name} отвечает...`;
        answeringStatus.classList.remove("hidden");
    }
}

function showVerdict({ verdict }) {
    answerInputContainer.classList.add("hidden");
    answeringStatus.classList.add("hidden");
    answerStatus.textContent = verdict;
    answerStatus.classList.remove("hidden");
    setBuzzerState("disabled");

    showToast(`Вердикт: ${verdict}`, "info");
    // Не скрываем question-view здесь.
    // Если ответ верный → придёт board_updated и renderBoardUpdate скроет question-view.
    // Если ответ неверный → придёт buzzer_activated и activateBuzzer восстановит buzzer.
}

function setBuzzerState(state) {
    btnBuzzer.classList.remove("disabled", "loading");
    if (state === "disabled") btnBuzzer.classList.add("disabled");
    if (state === "loading")  btnBuzzer.classList.add("loading");
}

/* ══════════════════════════════════════════
   РЕЗУЛЬТАТЫ
══════════════════════════════════════════ */
const PLACE_MEDALS = ["🥇", "🥈", "🥉"];

function showResults({ scores }) {
    gameFinished = true;
    // Скрываем всё игровое
    questionView.classList.add("hidden");
    lobbyView.classList.add("hidden");
    gameContainer.classList.remove("hidden");

    resultsList.innerHTML = "";
    scores.forEach(({ name, score }, i) => {
        const row = document.createElement("div");
        row.className = "result-row";
        row.innerHTML = `
            <span class="result-place">${PLACE_MEDALS[i] || `${i + 1}.`}</span>
            <span class="result-name">${name}</span>
            <span class="result-score">${score} очков</span>
        `;
        resultsList.appendChild(row);
    });

    resultsView.classList.remove("hidden");
    showToast("Игра завершена! Смотрите результаты.", "success", 5000);
}

btnPlayAgain.addEventListener("click", () => location.reload());

/* ══════════════════════════════════════════
   СЧЁТ
══════════════════════════════════════════ */
function updateScoreboard(scores) {
    scoreboard.innerHTML = "";
    Object.values(scores).forEach(({ name, score }) => {
        const chip = document.createElement("div");
        chip.className = "score-chip";
        chip.textContent = `${name}: ${score}`;
        scoreboard.appendChild(chip);
    });
}

/* ══════════════════════════════════════════
   ДЕЙСТВИЯ ИГРОКА
══════════════════════════════════════════ */
function selectQuestion(questionId) {
    sendEvent({ type: "select_question", question_id: questionId, username: playerName });
}

function submitAnswer() {
    const text = answerInput.value.trim();
    if (!text) return;
    if (sendEvent({ type: "submit_answer", text, username: playerName })) {
        answerInputContainer.classList.add("hidden");
        answerStatus.textContent = "Ответ отправлен. Ждём вердикт...";
        answerStatus.classList.remove("hidden");
    }
}

/* ══════════════════════════════════════════
   КНОПКИ
══════════════════════════════════════════ */
btnBuzzer.addEventListener("click", () => {
    if (btnBuzzer.classList.contains("disabled") || btnBuzzer.classList.contains("loading")) return;
    setBuzzerState("loading");
    sendEvent({ type: "buzzer_press", room_id: currentRoomId, username: playerName });
});

btnReady.addEventListener("click", () => {
    sendEvent({ type: "command", command: "/ready", username: playerName });
});

btnNotReady.addEventListener("click", () => {
    sendEvent({ type: "command", command: "/notready", username: playerName });
});

btnLeave.addEventListener("click", () => {
    if (confirm("Покинуть лобби?")) {
        sendEvent({ type: "command", command: "/leave", username: playerName });
        setTimeout(() => location.reload(), 500);
    }
});

btnSubmitAnswer.addEventListener("click", submitAnswer);

answerInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitAnswer();
});

/* ══════════════════════════════════════════
   ИНИЦИАЛИЗАЦИЯ
══════════════════════════════════════════ */
fetchLobbies();
// Обновляем список лобби каждые 5 секунд пока на экране входа
const lobbyInterval = setInterval(() => {
    if (!gameScreen.classList.contains("hidden")) {
        clearInterval(lobbyInterval);
        return;
    }
    fetchLobbies();
}, 5000);
