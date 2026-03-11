let socket = null;
let currentRoomId = null;
let playerName = "";
let gameState = {
    phase: "LOBBY",
    board: [],
    closedQuestions: [],
    scores: {}
};

// UI Elements
const joinScreen = document.getElementById('join-screen');
const gameScreen = document.getElementById('game-screen');
const lobbyList = document.getElementById('lobby-list');
const btnJoin = document.getElementById('btn-join');
const btnRefresh = document.getElementById('btn-refresh');
const playerNameInput = document.getElementById('player-name');
const boardView = document.getElementById('board-view');
const questionView = document.getElementById('question-view');
const btnBuzzer = document.getElementById('btn-buzzer');
const lobbyView = document.getElementById('lobby-view');
const playerList = document.getElementById('player-list');
const btnReady = document.getElementById('btn-ready');
const btnNotReady = document.getElementById('btn-notready');
const btnLeave = document.getElementById('btn-leave');
const gameContainer = document.getElementById('game-container');
const answerInputContainer = document.getElementById('answer-input-container');
const answerInput = document.getElementById('answer-input');
const btnSubmitAnswer = document.getElementById('btn-submit-answer');
const answerStatus = document.getElementById('answer-status');
const qText = document.getElementById('q-text');
const qPoints = document.getElementById('q-points');

// --- Lobby Logic ---

async function fetchLobbies() {
    lobbyList.innerHTML = '<div class="loader">Ищем игры...</div>';
    try {
        const response = await fetch('/rooms');
        const rooms = await response.json();
        
        lobbyList.innerHTML = '';
        if (rooms.length === 0) {
            lobbyList.innerHTML = '<div class="p-3">Активных игр не найдено. Создайте игру в Телеграме!</div>';
            return;
        }

        rooms.forEach(room => {
            const item = document.createElement('div');
            item.className = 'lobby-item';
            item.innerHTML = `
                <span class="lobby-id">Room: ${room.room_id}</span>
                <span class="lobby-players">👥 ${room.player_count} | Раунд: ${room.current_round}</span>
            `;
            item.onclick = () => selectLobby(room.room_id, item);
            lobbyList.appendChild(item);
        });
    } catch (e) {
        lobbyList.innerHTML = '<div class="p-3 text-danger">Ошибка загрузки списка лобби</div>';
    }
}

function selectLobby(roomId, element) {
    currentRoomId = roomId;
    document.querySelectorAll('.lobby-item').forEach(el => el.classList.remove('selected'));
    element.classList.add('selected');
    validateJoin();
}

function validateJoin() {
    playerName = playerNameInput.value.trim();
    btnJoin.disabled = !(currentRoomId && playerName);
}

playerNameInput.addEventListener('input', validateJoin);
btnRefresh.onclick = fetchLobbies;

btnJoin.onclick = () => {
    if (currentRoomId && playerName) {
        connectToGame(currentRoomId, playerName);
    }
};

// --- Game Socket Logic ---

function connectToGame(roomId, name) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/${roomId}/${encodeURIComponent(name)}`;
    
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        joinScreen.classList.add('hidden');
        gameScreen.classList.remove('hidden');
        document.getElementById('room-display').innerText = `Room: ${roomId}`;
    };

    socket.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleServerMessage(msg);
    };

    socket.onclose = () => {
        alert("Соединение потеряно. Вернитесь в меню.");
        location.reload();
    };
}

function handleServerMessage(msg) {
    const { event_type, payload } = msg;

    switch (event_type) {
        case 'board_updated':
            updateBoard(payload);
            break;
        case 'question_opened':
            showQuestion(payload);
            break;
        case 'buzzer_activated':
            enableBuzzer();
            break;
        case 'answering_started':
            handleAnsweringStarted(payload);
            break;
        case 'verdict_announced':
            handleVerdict(payload);
            break;
        case 'lobby_updated':
            updateLobby(payload);
            break;
    }

    // Toggle views based on phase
    if (gameState.phase === "LOBBY") {
        lobbyView.classList.remove('hidden');
        gameContainer.classList.add('hidden');
    } else {
        lobbyView.classList.add('hidden');
        gameContainer.classList.remove('hidden');
    }
}

// --- UI Updates ---

function updateLobby(data) {
    gameState.phase = "LOBBY";
    playerList.innerHTML = '';
    
    data.players.forEach(p => {
        const item = document.createElement('div');
        item.className = 'player-item';
        item.innerHTML = `
            <span class="player-name">${p.name}</span>
            <span class="ready-status ${p.is_ready ? 'status-ready' : 'status-waiting'}">
                ${p.is_ready ? 'ГОТОВ' : 'ОЖИДАНИЕ'}
            </span>
        `;
        playerList.appendChild(item);

        // Update own ready buttons
        if (p.id === playerName) {
            if (p.is_ready) {
                btnReady.classList.add('hidden');
                btnNotReady.classList.remove('hidden');
            } else {
                btnReady.classList.remove('hidden');
                btnNotReady.classList.add('hidden');
            }
        }
    });

    // Mirror to scoreboard for top bar consistency
    const scores = {};
    data.players.forEach(p => {
        scores[p.id] = { name: p.name, score: p.score || 0 };
    });
    updateScoreboard(scores);
}

function updateBoard(data) {
    gameState.phase = "GAME"; // If we receive board, we are in game
    gameState.board = data.board;
    gameState.closedQuestions = data.closed_questions || [];
    renderBoard();
    updateScoreboard(data.scores);
    document.getElementById('round-display').innerText = `Раунд: ${data.round_number} (${data.round_name})`;
}

function renderBoard() {
    boardView.innerHTML = '';
    if (!gameState.board || gameState.board.length === 0) return;

    // Генерируем сетку
    const themesCount = gameState.board.length;
    const questionsCount = gameState.board[0].questions.length;

    for (let i = 0; i < themesCount; i++) {
        const row = document.createElement('div');
        row.className = 'board-row';
        
        // Клетка темы
        const themeCell = document.createElement('div');
        themeCell.className = 'cell theme-cell';
        themeCell.innerText = gameState.board[i].theme;
        row.appendChild(themeCell);

        // Клетки вопросов
        gameState.board[i].questions.forEach(q => {
            const qCell = document.createElement('div');
            const isClosed = gameState.closedQuestions.includes(q.id);
            qCell.className = `cell ${isClosed ? 'closed' : ''}`;
            qCell.innerText = isClosed ? '×' : q.value;
            
            if (!isClosed) {
                qCell.onclick = () => selectQuestion(q.id);
            }
            row.appendChild(qCell);
        });
        boardView.appendChild(row);
    }
    questionView.classList.add('hidden');
}

function showQuestion(data) {
    document.getElementById('q-text').innerText = data.text;
    document.getElementById('q-points').innerText = data.value;
    questionView.classList.remove('hidden');
    btnBuzzer.classList.add('disabled'); // Ждем активации пищалки
}

function enableBuzzer() {
    btnBuzzer.classList.remove('disabled');
}

function closeQuestion() {
    questionView.classList.add('hidden');
    answerInputContainer.classList.add('hidden');
    answerStatus.classList.add('hidden');
    answerInput.value = '';
}

function handleAnsweringStarted(data) {
    btnBuzzer.classList.add('disabled');
    btnBuzzer.classList.remove('loading');
    if (data.player_id === playerName) {
        answerInputContainer.classList.remove('hidden');
        answerStatus.classList.add('hidden');
        answerInput.focus();
    } else {
        answerInputContainer.classList.add('hidden');
        answerStatus.innerText = `Отвечает ${data.name}...`;
        answerStatus.classList.remove('hidden');
    }
}

function handleVerdict(data) {
    // Show verdict briefly or just close
    answerStatus.innerText = `Вердикт: ${data.verdict}`;
    setTimeout(closeQuestion, 2000);
}

function submitAnswer() {
    const text = answerInput.value.trim();
    if (text && socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
            type: 'submit_answer',
            text: text,
            username: playerName
        }));
        answerInputContainer.classList.add('hidden');
        answerStatus.innerText = "Ответ отправлен. Ждем вердикт...";
        answerStatus.classList.remove('hidden');
    }
}

function updateScoreboard(scores) {
    const container = document.getElementById('scoreboard');
    container.innerHTML = '';
    for (const id in scores) {
        const p = scores[id];
        const div = document.createElement('div');
        div.className = 'player-score';
        div.innerText = `${p.name}: ${p.score}`;
        container.appendChild(div);
    }
}

// --- Actions ---

function selectQuestion(questionId) {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
            type: 'select_question',
            question_id: questionId,
            username: playerName
        }));
    }
}

btnBuzzer.onclick = () => {
    if (btnBuzzer.classList.contains('disabled') || btnBuzzer.classList.contains('loading')) return;
    
    if (socket && socket.readyState === WebSocket.OPEN) {
        btnBuzzer.classList.add('loading');
        socket.send(JSON.stringify({ 
            type: 'buzzer_press',
            room_id: currentRoomId,
            username: playerName
        }));
    }
};

btnReady.onclick = () => {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'command', command: '/ready', username: playerName }));
    }
};

btnNotReady.onclick = () => {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'command', command: '/notready', username: playerName }));
    }
};

btnLeave.onclick = () => {
    if (socket && socket.readyState === WebSocket.OPEN) {
        if (confirm("Выйти из лобби?")) {
            socket.send(JSON.stringify({ type: 'command', command: '/leave', username: playerName }));
            location.reload();
        }
    }
};

btnSubmitAnswer.onclick = submitAnswer;
answerInput.onkeydown = (e) => {
    if (e.key === 'Enter') submitAnswer();
};

// Start
fetchLobbies();
setInterval(fetchLobbies, 5000); // Обновляем список каждые 5 сек
