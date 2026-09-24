/**
 * HYPER CHAT - MULTI-USER SPATIAL SECTOR CLIENT
 * File: frontend/rooms.js
 * Role: Member 2 (Frontend Developer)
 * 
 * Out-of-the-box features:
 * - Sector portal selection (#quantum-core, #cyber-deck, #hyper-lounge, #neon-arcade)
 * - Interactive 60fps Starfield / Neural Constellation Canvas
 * - 3D Parallax Tilt Deck
 * - Native Web Audio Synthesizer (Zero external dependencies)
 * - Dynamic Theme Matrix (Nebula, Cyberpunk, Synthwave)
 * - Interactive Message Particle Blast on transmission
 * - Quick Reaction Holographic HUD
 * - Target endpoint: ws://localhost:8000/ws/{room}/{username}
 */

(() => {
  'use strict';

  // ==========================================================================
  // STATE MANAGEMENT
  // ==========================================================================
  const state = {
    currentUser: '',
    currentRoom: 'quantum-core',
    socket: null,
    onlineUsers: [],
    isConnecting: false,
    isConnected: false,
    hasLoadedHistory: false,
    userScrolledUp: false,
    soundEnabled: localStorage.getItem('hyper_chat_sound') !== 'false',
    currentTheme: localStorage.getItem('hyper_chat_theme') || 'nebula'
  };

  // ==========================================================================
  // DOM ELEMENTS
  // ==========================================================================
  const elements = {
    matrixCanvas: document.getElementById('matrix-canvas'),
    parallaxCard: document.getElementById('parallax-card'),

    // Screens
    joinScreen: document.getElementById('join-screen'),
    chatScreen: document.getElementById('chat-screen'),

    // Join Screen Elements
    joinForm: document.getElementById('join-form'),
    usernameInput: document.getElementById('username-input'),
    roomInput: document.getElementById('room-input'),
    serverUrlInput: document.getElementById('server-url-input'),
    joinBtn: document.getElementById('join-btn'),
    joinBtnText: document.querySelector('#join-btn .btn-text'),
    joinBtnSpinner: document.querySelector('#join-btn .btn-spinner'),
    joinError: document.getElementById('join-error'),
    presetButtons: document.querySelectorAll('.room-preset-btn'),
    joinAvatarPreview: document.getElementById('join-avatar-preview'),
    avatarSubText: document.getElementById('avatar-sub-text'),

    // Chat Header Elements
    roomDisplayName: document.getElementById('room-display-name'),
    connectionStatus: document.getElementById('connection-status'),
    currentUserAvatar: document.getElementById('current-user-avatar'),
    currentUserName: document.getElementById('current-user-name'),
    leaveBtn: document.getElementById('leave-btn'),
    toggleSidebarBtn: document.getElementById('toggle-sidebar-btn'),
    themeBtn: document.getElementById('theme-btn'),
    soundBtn: document.getElementById('sound-btn'),
    soundIcon: document.getElementById('sound-icon'),

    // Sidebar Elements
    sidebar: document.getElementById('online-users-sidebar'),
    sidebarOverlay: document.getElementById('sidebar-overlay'),
    usersList: document.getElementById('users-list'),
    onlineCount: document.getElementById('online-count'),

    // Chat Feed Elements
    chatAlert: document.getElementById('chat-alert'),
    messagesContainer: document.getElementById('messages-container'),
    emptyState: document.getElementById('empty-state'),
    scrollBottomBtn: document.getElementById('scroll-bottom-btn'),

    // Reactions & Input
    quickReactionBar: document.getElementById('quick-reaction-bar'),
    messageForm: document.getElementById('message-form'),
    messageInput: document.getElementById('message-input'),
    sendBtn: document.getElementById('send-btn')
  };

  const AVATAR_GRADIENTS = [
    'linear-gradient(135deg, #00f0ff, #7000ff)',
    'linear-gradient(135deg, #a855f7, #ff007f)',
    'linear-gradient(135deg, #00ffaa, #00b4d8)',
    'linear-gradient(135deg, #ff007f, #ffb703)',
    'linear-gradient(135deg, #7928ca, #ff0080)',
    'linear-gradient(135deg, #00f5d4, #7b2cbf)'
  ];

  // ==========================================================================
  // NATIVE WEB AUDIO SYNTHESIZER
  // ==========================================================================
  let audioCtx = null;

  function getAudioContext() {
    if (!audioCtx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) {
        audioCtx = new AudioContextClass();
      }
    }
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    return audioCtx;
  }

  function playTone(freq, type, duration, gainVal = 0.1) {
    if (!state.soundEnabled) return;
    try {
      const ctx = getAudioContext();
      if (!ctx) return;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, ctx.currentTime);
      gain.gain.setValueAtTime(gainVal, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + duration);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + duration);
    } catch {}
  }

  function playJoinSound() {
    if (!state.soundEnabled) return;
    try {
      const ctx = getAudioContext();
      if (!ctx) return;
      [520, 680, 920, 1200].forEach((freq, idx) => {
        setTimeout(() => playTone(freq, 'sine', 0.2, 0.08), idx * 80);
      });
    } catch {}
  }

  function playSendSound() {
    if (!state.soundEnabled) return;
    try {
      const ctx = getAudioContext();
      if (!ctx) return;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(1100, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(400, ctx.currentTime + 0.14);
      gain.gain.setValueAtTime(0.12, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.14);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.14);
    } catch {}
  }

  function playReceiveSound() {
    if (!state.soundEnabled) return;
    try {
      const ctx = getAudioContext();
      if (!ctx) return;
      playTone(750, 'sine', 0.22, 0.09);
      setTimeout(() => playTone(1150, 'sine', 0.28, 0.07), 70);
    } catch {}
  }

  function playPresenceSound(isJoin = true) {
    if (!state.soundEnabled) return;
    const baseFreq = isJoin ? 560 : 420;
    playTone(baseFreq, 'sine', 0.35, 0.06);
  }

  // ==========================================================================
  // THEME ENGINE
  // ==========================================================================
  const THEMES = ['nebula', 'cyberpunk', 'synthwave'];

  function applyTheme(themeName) {
    if (!THEMES.includes(themeName)) themeName = 'nebula';
    state.currentTheme = themeName;
    document.documentElement.setAttribute('data-theme', themeName);
    localStorage.setItem('hyper_chat_theme', themeName);
  }

  function cycleTheme() {
    const nextIdx = (THEMES.indexOf(state.currentTheme) + 1) % THEMES.length;
    applyTheme(THEMES[nextIdx]);
  }

  applyTheme(state.currentTheme);

  // ==========================================================================
  // INTERACTIVE CANVAS
  // ==========================================================================
  function initNeuralCanvas() {
    const canvas = elements.matrixCanvas;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let width = canvas.width = window.innerWidth;
    let height = canvas.height = window.innerHeight;

    const mouse = { x: -1000, y: -1000 };
    const numNodes = Math.min(Math.floor((width * height) / 18000), 55);
    const nodes = [];

    class Node {
      constructor() {
        this.x = Math.random() * width;
        this.y = Math.random() * height;
        this.vx = (Math.random() - 0.5) * 0.75;
        this.vy = (Math.random() - 0.5) * 0.75;
        this.radius = Math.random() * 2 + 1.2;
      }
      update() {
        this.x += this.vx;
        this.y += this.vy;
        if (this.x < 0) this.x = width;
        else if (this.x > width) this.x = 0;
        if (this.y < 0) this.y = height;
        else if (this.y > height) this.y = 0;
      }
      draw() {
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(168, 85, 247, 0.75)';
        ctx.shadowBlur = 8;
        ctx.shadowColor = '#a855f7';
        ctx.fill();
        ctx.shadowBlur = 0;
      }
    }

    for (let i = 0; i < numNodes; i++) {
      nodes.push(new Node());
    }

    window.addEventListener('resize', () => {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    });

    window.addEventListener('mousemove', (e) => {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
    });

    window.addEventListener('mouseleave', () => {
      mouse.x = -1000;
      mouse.y = -1000;
    });

    function render() {
      ctx.clearRect(0, 0, width, height);

      for (let i = 0; i < nodes.length; i++) {
        nodes[i].update();
        nodes[i].draw();

        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < 110) {
            const alpha = (1 - dist / 110) * 0.28;
            ctx.beginPath();
            ctx.moveTo(nodes[i].x, nodes[i].y);
            ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.strokeStyle = `rgba(168, 85, 247, ${alpha})`;
            ctx.lineWidth = 1;
            ctx.stroke();
          }
        }

        const mdx = nodes[i].x - mouse.x;
        const mdy = nodes[i].y - mouse.y;
        const mdist = Math.sqrt(mdx * mdx + mdy * mdy);
        if (mdist < 140) {
          const mAlpha = (1 - mdist / 140) * 0.55;
          ctx.beginPath();
          ctx.moveTo(nodes[i].x, nodes[i].y);
          ctx.lineTo(mouse.x, mouse.y);
          ctx.strokeStyle = `rgba(0, 240, 255, ${mAlpha})`;
          ctx.lineWidth = 1.3;
          ctx.stroke();
        }
      }

      requestAnimationFrame(render);
    }

    render();
  }

  // ==========================================================================
  // 3D PARALLAX TILT
  // ==========================================================================
  function initParallaxTilt() {
    const card = elements.parallaxCard;
    const screen = elements.joinScreen;
    if (!card || !screen) return;

    screen.addEventListener('mousemove', (e) => {
      const rect = card.getBoundingClientRect();
      const cardCenterX = rect.left + rect.width / 2;
      const cardCenterY = rect.top + rect.height / 2;

      const normX = (e.clientX - cardCenterX) / (window.innerWidth / 2);
      const normY = (e.clientY - cardCenterY) / (window.innerHeight / 2);

      const rotateY = normX * 12;
      const rotateX = -normY * 12;

      card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(1.02, 1.02, 1.02)`;
    });

    screen.addEventListener('mouseleave', () => {
      card.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)';
    });
  }

  // ==========================================================================
  // SPARKLE BURST
  // ==========================================================================
  function triggerParticleBurst(originX, originY) {
    const burstContainer = document.createElement('div');
    burstContainer.style.position = 'fixed';
    burstContainer.style.left = `${originX}px`;
    burstContainer.style.top = `${originY}px`;
    burstContainer.style.pointerEvents = 'none';
    burstContainer.style.zIndex = '9999';
    document.body.appendChild(burstContainer);

    const sparks = 16;
    for (let i = 0; i < sparks; i++) {
      const spark = document.createElement('div');
      const angle = (Math.PI * 2 * i) / sparks + (Math.random() - 0.5) * 0.4;
      const distance = Math.random() * 50 + 25;
      const tx = Math.cos(angle) * distance;
      const ty = Math.sin(angle) * distance;
      const color = i % 2 === 0 ? 'var(--neon-violet)' : 'var(--neon-cyan)';

      spark.style.position = 'absolute';
      spark.style.width = '6px';
      spark.style.height = '6px';
      spark.style.borderRadius = '50%';
      spark.style.backgroundColor = color;
      spark.style.boxShadow = `0 0 10px ${color}`;
      spark.style.transition = 'all 0.5s cubic-bezier(0.16, 1, 0.3, 1)';

      burstContainer.appendChild(spark);

      requestAnimationFrame(() => {
        spark.style.transform = `translate(${tx}px, ${ty}px) scale(0)`;
        spark.style.opacity = '0';
      });
    }

    setTimeout(() => burstContainer.remove(), 600);
  }

  // ==========================================================================
  // UTILITIES
  // ==========================================================================
  function getUserGradient(username) {
    if (!username) return AVATAR_GRADIENTS[0];
    let hash = 0;
    for (let i = 0; i < username.length; i++) {
      hash = username.charCodeAt(i) + ((hash << 5) - hash);
    }
    const index = Math.abs(hash) % AVATAR_GRADIENTS.length;
    return AVATAR_GRADIENTS[index];
  }

  function getUserInitials(username) {
    if (!username) return '?';
    const trimmed = username.trim();
    if (trimmed.length <= 2) return trimmed.toUpperCase();
    const parts = trimmed.split(/[\s_.-]+/);
    if (parts.length > 1 && parts[0] && parts[1]) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return trimmed.substring(0, 2).toUpperCase();
  }

  function formatTimestamp(rawTimestamp) {
    if (!rawTimestamp) {
      return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    try {
      const date = new Date(rawTimestamp);
      if (isNaN(date.getTime())) {
        return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      }
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text ?? '';
    return div.innerHTML;
  }

  function showJoinError(message) {
    elements.joinError.textContent = message;
    elements.joinError.classList.remove('hidden');
  }

  function hideJoinError() {
    elements.joinError.textContent = '';
    elements.joinError.classList.add('hidden');
  }

  let toastTimeout = null;
  function showChatToast(message) {
    if (toastTimeout) clearTimeout(toastTimeout);
    elements.chatAlert.textContent = message;
    elements.chatAlert.classList.remove('hidden');

    toastTimeout = setTimeout(() => {
      elements.chatAlert.classList.add('hidden');
    }, 4500);
  }

  function setJoinLoading(loading) {
    state.isConnecting = loading;
    elements.joinBtn.disabled = loading;
    elements.usernameInput.disabled = loading;
    elements.roomInput.disabled = loading;
    if (loading) {
      elements.joinBtnText.textContent = 'WARPING TO SECTOR...';
      elements.joinBtnSpinner.classList.remove('hidden');
    } else {
      elements.joinBtnText.textContent = 'WARP TO SECTOR 🛸';
      elements.joinBtnSpinner.classList.add('hidden');
    }
  }

  function updateConnectionStatus(text) {
    elements.connectionStatus.textContent = text;
  }

  function switchToChatScreen() {
    elements.joinScreen.classList.add('hidden');
    elements.joinScreen.classList.remove('active');
    elements.chatScreen.classList.remove('hidden');
    elements.chatScreen.classList.add('active');

    elements.roomDisplayName.textContent = `#${state.currentRoom}`;
    elements.currentUserName.textContent = state.currentUser;
    elements.currentUserAvatar.textContent = getUserInitials(state.currentUser);
    elements.currentUserAvatar.style.background = getUserGradient(state.currentUser);

    updateConnectionStatus('QUANTUM SYNC ACTIVE');
    playJoinSound();
    elements.messageInput.focus();
  }

  function switchToJoinScreen() {
    elements.chatScreen.classList.add('hidden');
    elements.chatScreen.classList.remove('active');
    elements.joinScreen.classList.remove('hidden');
    elements.joinScreen.classList.add('active');
    setJoinLoading(false);
    elements.usernameInput.focus();
  }

  // ==========================================================================
  // WEBSOCKET MANAGEMENT
  // Endpoint: ws://localhost:8000/ws/{room}/{username}
  // ==========================================================================
  function connectWebSocket(username, room) {
    let baseUrl = elements.serverUrlInput.value.trim();
    if (!baseUrl) {
      baseUrl = 'ws://localhost:8000/ws';
    }
    baseUrl = baseUrl.replace(/\/+$/, '');
    const wsUrl = `${baseUrl}/${encodeURIComponent(room)}/${encodeURIComponent(username)}`;

    hideJoinError();
    setJoinLoading(true);

    try {
      state.socket = new WebSocket(wsUrl);
    } catch (err) {
      setJoinLoading(false);
      showJoinError(`Invalid WebSocket endpoint: ${err.message}`);
      return;
    }

    state.socket.onopen = () => {
      state.isConnected = true;
      state.isConnecting = false;
      setJoinLoading(false);
      switchToChatScreen();
    };

    state.socket.onmessage = (event) => {
      handleIncomingMessage(event.data);
    };

    state.socket.onerror = (err) => {
      console.error('WebSocket Error:', err);
      if (!state.isConnected) {
        setJoinLoading(false);
        showJoinError('Could not establish link. Is the FastAPI backend running?');
      } else {
        showChatToast('Quantum signal anomaly detected');
      }
    };

    state.socket.onclose = (event) => {
      const wasConnected = state.isConnected;
      state.isConnected = false;
      state.isConnecting = false;
      state.socket = null;

      if (!wasConnected) {
        setJoinLoading(false);
        showJoinError(event.reason || 'Failed to establish link with sector.');
      } else {
        updateConnectionStatus('SECTOR OFFLINE');
        showChatToast('Sector link severed.');
        appendSystemNotification('Disconnected from sector transmission.', 'leave');
      }
    };
  }

  function disconnect(isUserInitiated = true) {
    if (state.socket) {
      state.socket.onclose = null;
      state.socket.close();
      state.socket = null;
    }

    state.isConnected = false;
    state.isConnecting = false;
    state.onlineUsers = [];
    state.hasLoadedHistory = false;

    elements.messagesContainer.querySelectorAll('.message-row, .system-notice').forEach(el => el.remove());
    elements.emptyState.classList.remove('hidden');
    elements.usersList.innerHTML = '';
    elements.onlineCount.textContent = '0';

    if (isUserInitiated) {
      switchToJoinScreen();
    }
  }

  function sendChatMessage(text) {
    if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
      showChatToast('Transceiver offline: Cannot transmit signal');
      return;
    }

    const payload = {
      type: 'chat_message',
      data: {
        message: text
      }
    };

    try {
      state.socket.send(JSON.stringify(payload));
      playSendSound();
    } catch (err) {
      console.error('Failed to send message:', err);
      showChatToast('Failed to broadcast transmission');
    }
  }

  // ==========================================================================
  // INBOUND MESSAGE DISPATCHER
  // ==========================================================================
  function handleIncomingMessage(rawMessage) {
    let parsed;
    try {
      parsed = JSON.parse(rawMessage);
    } catch (err) {
      console.error('Failed to parse WebSocket JSON:', rawMessage, err);
      return;
    }

    if (!parsed || !parsed.type) return;
    const { type, data } = parsed;

    switch (type) {
      case 'chat_message':
        onChatMessageReceived(data);
        break;
      case 'user_joined':
        onUserJoinedReceived(data);
        break;
      case 'user_left':
        onUserLeftReceived(data);
        break;
      case 'online_users':
        onOnlineUsersReceived(data);
        break;
      case 'chat_history':
        onChatHistoryReceived(data);
        break;
      case 'error':
        onErrorReceived(data);
        break;
    }
  }

  function onChatMessageReceived(data) {
    if (!data) return;
    elements.emptyState.classList.add('hidden');

    const username = data.username || 'Anonymous';
    const message = data.message || '';
    const timestamp = data.timestamp || new Date().toISOString();
    const isSelf = username.toLowerCase() === state.currentUser.toLowerCase();

    if (!isSelf) {
      playReceiveSound();
    }

    renderChatMessage({
      messageId: data.message_id,
      username,
      message,
      timestamp,
      isSelf
    });

    scrollToBottomIfNeeded(isSelf);
  }

  function onUserJoinedReceived(data) {
    const joinedUsername = (typeof data === 'string') 
      ? data 
      : (data?.username || data?.user || 'Unknown Pilot');

    if (joinedUsername.toLowerCase() === state.currentUser.toLowerCase()) {
      appendSystemNotification(`Synchronized with Sector #${state.currentRoom}`, 'join');
    } else {
      appendSystemNotification(`Pilot [${joinedUsername}] entered sector`, 'join');
      playPresenceSound(true);
    }

    if (!state.onlineUsers.some(u => u.toLowerCase() === joinedUsername.toLowerCase())) {
      state.onlineUsers.push(joinedUsername);
      renderOnlineUsersList();
    }

    scrollToBottomIfNeeded(false);
  }

  function onUserLeftReceived(data) {
    const leftUsername = (typeof data === 'string') 
      ? data 
      : (data?.username || data?.user || 'Unknown Pilot');

    appendSystemNotification(`Pilot [${leftUsername}] exited sector`, 'leave');
    playPresenceSound(false);

    state.onlineUsers = state.onlineUsers.filter(u => u.toLowerCase() !== leftUsername.toLowerCase());
    renderOnlineUsersList();
    scrollToBottomIfNeeded(false);
  }

  function onOnlineUsersReceived(data) {
    let users = [];
    if (Array.isArray(data)) users = data;
    else if (data && Array.isArray(data.users)) users = data.users;

    if (state.currentUser && !users.some(u => u.toLowerCase() === state.currentUser.toLowerCase())) {
      users.unshift(state.currentUser);
    }

    state.onlineUsers = users;
    renderOnlineUsersList();
  }

  function onChatHistoryReceived(data) {
    let messages = [];
    if (Array.isArray(data)) messages = data;
    else if (data && Array.isArray(data.messages)) messages = data.messages;

    elements.messagesContainer.querySelectorAll('.message-row, .system-notice').forEach(el => el.remove());

    if (messages.length === 0) {
      elements.emptyState.classList.remove('hidden');
      return;
    }

    elements.emptyState.classList.add('hidden');
    appendSystemNotification(`Transmission logs loaded for #${state.currentRoom}`, 'join');

    messages.forEach((msg) => {
      const username = msg.username || 'Anonymous';
      const message = msg.message || '';
      const timestamp = msg.timestamp || '';
      const isSelf = username.toLowerCase() === state.currentUser.toLowerCase();

      renderChatMessage({
        messageId: msg.message_id,
        username,
        message,
        timestamp,
        isSelf
      });
    });

    state.hasLoadedHistory = true;
    scrollToBottom(true);
  }

  function onErrorReceived(data) {
    const errorMsg = (typeof data === 'string')
      ? data
      : (data?.message || data?.detail || 'An anomaly occurred on the server.');

    if (!state.isConnected) {
      showJoinError(errorMsg);
    } else {
      showChatToast(`Alert: ${errorMsg}`);
      appendSystemNotification(`Alert: ${errorMsg}`, 'leave');
    }
  }

  // ==========================================================================
  // DOM RENDERING
  // ==========================================================================
  function renderChatMessage({ messageId, username, message, timestamp, isSelf }) {
    const row = document.createElement('div');
    row.className = `message-row ${isSelf ? 'outgoing' : 'incoming'}`;
    if (messageId) row.dataset.messageId = messageId;

    const timeFormatted = formatTimestamp(timestamp);
    const userGradient = getUserGradient(username);
    const initials = getUserInitials(username);

    let avatarHtml = '';
    if (!isSelf) {
      avatarHtml = `
        <div class="msg-avatar" style="background: ${userGradient};" title="${escapeHtml(username)}">
          ${escapeHtml(initials)}
        </div>
      `;
    }

    row.innerHTML = `
      ${avatarHtml}
      <div class="message-bubble">
        <div class="message-sender">
          <span>${escapeHtml(isSelf ? 'YOU' : `@${username}`)}</span>
        </div>
        <div class="message-text">${escapeHtml(message)}</div>
        <div class="message-meta">
          <span class="message-time">${timeFormatted}</span>
          ${isSelf ? `
            <svg class="check-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
          ` : ''}
        </div>
      </div>
    `;

    elements.messagesContainer.appendChild(row);
  }

  function appendSystemNotification(text, type = 'join') {
    elements.emptyState.classList.add('hidden');

    const el = document.createElement('div');
    el.className = `system-notice ${type}`;

    let icon = '⚡';
    if (type === 'join') icon = '🟢';
    else if (type === 'leave') icon = '🟠';

    el.innerHTML = `<span>${icon}</span> <span>${escapeHtml(text)}</span>`;
    elements.messagesContainer.appendChild(el);
  }

  function renderOnlineUsersList() {
    elements.usersList.innerHTML = '';
    elements.onlineCount.textContent = state.onlineUsers.length.toString();

    const sorted = [...state.onlineUsers].sort((a, b) => {
      const aIsSelf = a.toLowerCase() === state.currentUser.toLowerCase();
      const bIsSelf = b.toLowerCase() === state.currentUser.toLowerCase();
      if (aIsSelf) return -1;
      if (bIsSelf) return 1;
      return a.localeCompare(b);
    });

    sorted.forEach((user) => {
      const isSelf = user.toLowerCase() === state.currentUser.toLowerCase();
      const li = document.createElement('li');
      li.className = 'user-item';

      const userGradient = getUserGradient(user);
      const initials = getUserInitials(user);

      li.innerHTML = `
        <div class="user-avatar-wrap">
          <div class="user-node-avatar" style="background: ${userGradient};">
            ${escapeHtml(initials)}
          </div>
          <span class="user-node-status"></span>
        </div>
        <div class="user-info">
          <span class="user-name">${escapeHtml(user)} ${isSelf ? '(You)' : ''}</span>
          <span class="user-status-text">Synchronized</span>
        </div>
      `;

      elements.usersList.appendChild(li);
    });
  }

  function scrollToBottom(immediate = false) {
    const container = elements.messagesContainer;
    if (immediate) {
      container.scrollTop = container.scrollHeight;
    } else {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: 'smooth'
      });
    }
    state.userScrolledUp = false;
    elements.scrollBottomBtn.classList.add('hidden');
  }

  function scrollToBottomIfNeeded(force = false) {
    if (force || !state.userScrolledUp) {
      scrollToBottom();
    } else {
      elements.scrollBottomBtn.classList.remove('hidden');
    }
  }

  elements.messagesContainer.addEventListener('scroll', () => {
    const container = elements.messagesContainer;
    const scrollPosition = container.scrollTop + container.clientHeight;
    const distanceToBottom = container.scrollHeight - scrollPosition;

    if (distanceToBottom > 100) {
      state.userScrolledUp = true;
    } else {
      state.userScrolledUp = false;
      elements.scrollBottomBtn.classList.add('hidden');
    }
  });

  elements.scrollBottomBtn.addEventListener('click', () => {
    scrollToBottom();
  });

  // ==========================================================================
  // EVENT LISTENERS
  // ==========================================================================
  elements.usernameInput.addEventListener('input', () => {
    const val = elements.usernameInput.value.trim();
    if (val) {
      elements.joinAvatarPreview.textContent = getUserInitials(val);
      elements.joinAvatarPreview.style.background = getUserGradient(val);
      elements.avatarSubText.textContent = `Callsign: @${val}`;
    } else {
      elements.joinAvatarPreview.textContent = '?';
      elements.joinAvatarPreview.style.background = 'linear-gradient(135deg, var(--neon-cyan), var(--neon-violet))';
      elements.avatarSubText.textContent = 'Enter callsign to calibrate beacon';
    }
  });

  // Room Preset Buttons
  elements.presetButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      elements.presetButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      elements.roomInput.value = btn.dataset.room;
      playTone(840, 'sine', 0.1, 0.07);
    });
  });

  elements.roomInput.addEventListener('input', () => {
    const currentVal = elements.roomInput.value.trim().toLowerCase();
    elements.presetButtons.forEach(btn => {
      if (btn.dataset.room.toLowerCase() === currentVal) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
  });

  // Sound FX Toggle
  function updateSoundUI() {
    if (elements.soundIcon) {
      elements.soundIcon.textContent = state.soundEnabled ? '🔊 SFX ON' : '🔇 SFX OFF';
    }
  }
  updateSoundUI();

  elements.soundBtn.addEventListener('click', () => {
    state.soundEnabled = !state.soundEnabled;
    localStorage.setItem('hyper_chat_sound', state.soundEnabled);
    updateSoundUI();
    if (state.soundEnabled) playTone(880, 'sine', 0.15, 0.1);
  });

  elements.themeBtn.addEventListener('click', () => {
    cycleTheme();
    playTone(660, 'sine', 0.12, 0.08);
  });

  if (elements.quickReactionBar) {
    elements.quickReactionBar.addEventListener('click', (e) => {
      const btn = e.target.closest('.reaction-btn');
      if (!btn) return;
      const emoji = btn.dataset.emoji;
      elements.messageInput.value += ` ${emoji} `;
      elements.messageInput.focus();
      playTone(900, 'sine', 0.08, 0.06);
    });
  }

  elements.joinForm.addEventListener('submit', (e) => {
    e.preventDefault();
    if (state.isConnecting) return;

    const rawUsername = elements.usernameInput.value.trim();
    const rawRoom = elements.roomInput.value.trim().replace(/^#+/, '');

    if (!rawUsername) {
      showJoinError('Please enter a callsign.');
      return;
    }

    if (!rawRoom) {
      showJoinError('Please enter or select a sector frequency.');
      return;
    }

    if (rawUsername.length < 2 || rawUsername.length > 25) {
      showJoinError('Callsign must be 2 to 25 characters.');
      return;
    }

    if (!/^[a-zA-Z0-9_-]+$/.test(rawUsername)) {
      showJoinError('Callsign can only contain letters, numbers, hyphens, and underscores.');
      return;
    }

    if (!/^[a-zA-Z0-9_-]+$/.test(rawRoom)) {
      showJoinError('Sector name can only contain letters, numbers, hyphens, and underscores.');
      return;
    }

    state.currentUser = rawUsername;
    state.currentRoom = rawRoom;
    connectWebSocket(rawUsername, rawRoom);
  });

  elements.messageForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = elements.messageInput.value.trim();
    if (!text) return;

    const sendRect = elements.sendBtn.getBoundingClientRect();
    triggerParticleBurst(sendRect.left + sendRect.width / 2, sendRect.top + sendRect.height / 2);

    sendChatMessage(text);
    elements.messageInput.value = '';
    elements.messageInput.focus();
  });

  elements.leaveBtn.addEventListener('click', () => {
    if (confirm(`Exit Sector #${state.currentRoom}?`)) {
      disconnect(true);
    }
  });

  elements.toggleSidebarBtn.addEventListener('click', () => {
    elements.sidebar.classList.toggle('open');
    elements.sidebarOverlay.classList.toggle('active');
  });

  elements.sidebarOverlay.addEventListener('click', () => {
    elements.sidebar.classList.remove('open');
    elements.sidebarOverlay.classList.remove('active');
  });

  initNeuralCanvas();
  initParallaxTilt();

})();
