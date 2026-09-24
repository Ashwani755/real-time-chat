/**
 * Real-Time Chat Application - Frontend Client
 * Role: Member 2 (Frontend Developer)
 * 
 * Features:
 * - WebSocket connection management to `ws://localhost:8000/ws/{username}`
 * - Strict adherence to agreed JSON protocol
 * - Message rendering with sender name, timestamp, and distinct outgoing/incoming styling
 * - Online users sidebar with live updates and user count
 * - System notifications for user_joined, user_left, and errors
 * - Chat history rendering
 * - Auto-scrolling with new message indicator
 * - Clean UI state transitions and error handling
 */

(() => {
  'use strict';

  // ==========================================================================
  // STATE MANAGEMENT
  // ==========================================================================
  const state = {
    currentUser: '',
    socket: null,
    onlineUsers: [],
    isConnecting: false,
    isConnected: false,
    hasLoadedHistory: false,
    userScrolledUp: false
  };

  // ==========================================================================
  // DOM ELEMENTS
  // ==========================================================================
  const elements = {
    // Screens
    joinScreen: document.getElementById('join-screen'),
    chatScreen: document.getElementById('chat-screen'),

    // Join Screen Elements
    joinForm: document.getElementById('join-form'),
    usernameInput: document.getElementById('username-input'),
    serverUrlInput: document.getElementById('server-url-input'),
    joinBtn: document.getElementById('join-btn'),
    joinBtnText: document.querySelector('#join-btn .btn-text'),
    joinBtnSpinner: document.querySelector('#join-btn .btn-spinner'),
    joinError: document.getElementById('join-error'),
    joinAvatarPreview: document.getElementById('join-avatar-preview'),
    avatarSubText: document.getElementById('avatar-sub-text'),

    // Chat Header Elements
    connectionStatus: document.getElementById('connection-status'),
    statusIndicator: document.querySelector('.header-status-indicator'),
    currentUserAvatar: document.getElementById('current-user-avatar'),
    currentUserName: document.getElementById('current-user-name'),
    leaveBtn: document.getElementById('leave-btn'),
    toggleSidebarBtn: document.getElementById('toggle-sidebar-btn'),

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

    // Message Input Elements
    messageForm: document.getElementById('message-form'),
    messageInput: document.getElementById('message-input'),
    sendBtn: document.getElementById('send-btn')
  };

  // Color generator for consistent user avatar backgrounds
  const AVATAR_COLORS = [
    '#ef4444', '#f97316', '#f59e0b', '#10b981', '#06b6d4',
    '#3b82f6', '#6366f1', '#8b5cf6', '#ec4899', '#14b8a6'
  ];

  // ==========================================================================
  // UTILITY FUNCTIONS
  // ==========================================================================

  /**
   * Returns a deterministic background color for a username.
   */
  function getUserColor(username) {
    if (!username) return AVATAR_COLORS[0];
    let hash = 0;
    for (let i = 0; i < username.length; i++) {
      hash = username.charCodeAt(i) + ((hash << 5) - hash);
    }
    const index = Math.abs(hash) % AVATAR_COLORS.length;
    return AVATAR_COLORS[index];
  }

  /**
   * Returns 1 or 2 uppercase letters representing initials.
   */
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

  /**
   * Formats a raw timestamp (ISO string or unix timestamp) into human readable time.
   */
  function formatTimestamp(rawTimestamp) {
    if (!rawTimestamp) {
      return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    try {
      const date = new Date(rawTimestamp);
      if (isNaN(date.getTime())) {
        return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      }
      
      const now = new Date();
      const isToday = date.toDateString() === now.toDateString();
      const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

      if (isToday) {
        return timeStr;
      }
      const monthDate = date.toLocaleDateString([], { month: 'short', day: 'numeric' });
      return `${monthDate}, ${timeStr}`;
    } catch {
      return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
  }

  /**
   * Escapes HTML text to prevent XSS vulnerabilities.
   */
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text ?? '';
    return div.innerHTML;
  }

  // ==========================================================================
  // UI DISPLAY & SCREEN TRANSITIONS
  // ==========================================================================

  function showJoinError(message) {
    elements.joinError.textContent = message;
    elements.joinError.classList.remove('hidden');
  }

  function hideJoinError() {
    elements.joinError.textContent = '';
    elements.joinError.classList.add('hidden');
  }

  let toastTimeout = null;
  function showChatToast(message, isError = true) {
    if (toastTimeout) clearTimeout(toastTimeout);
    elements.chatAlert.textContent = message;
    elements.chatAlert.style.backgroundColor = isError ? 'var(--color-danger-bg)' : 'var(--bg-surface-elevated)';
    elements.chatAlert.style.borderColor = isError ? 'var(--color-danger)' : 'var(--border-color)';
    elements.chatAlert.style.color = isError ? '#b91c1c' : 'var(--text-main)';
    elements.chatAlert.classList.remove('hidden');

    toastTimeout = setTimeout(() => {
      elements.chatAlert.classList.add('hidden');
    }, 4500);
  }

  function setJoinLoading(loading) {
    state.isConnecting = loading;
    elements.joinBtn.disabled = loading;
    elements.usernameInput.disabled = loading;
    if (loading) {
      elements.joinBtnText.textContent = 'Connecting...';
      elements.joinBtnSpinner.classList.remove('hidden');
    } else {
      elements.joinBtnText.textContent = 'Join Chat Room';
      elements.joinBtnSpinner.classList.add('hidden');
    }
  }

  function updateConnectionStatus(status, text) {
    elements.connectionStatus.textContent = text;
    elements.connectionStatus.className = `connection-status ${status}`;
    elements.statusIndicator.className = `header-status-indicator ${status}`;
  }

  function switchToChatScreen() {
    elements.joinScreen.classList.add('hidden');
    elements.chatScreen.classList.remove('hidden');

    // Update user header badge
    elements.currentUserName.textContent = state.currentUser;
    elements.currentUserAvatar.textContent = getUserInitials(state.currentUser);
    elements.currentUserAvatar.style.backgroundColor = getUserColor(state.currentUser);

    updateConnectionStatus('online', 'Connected');
    elements.messageInput.focus();
  }

  function switchToJoinScreen() {
    elements.chatScreen.classList.add('hidden');
    elements.joinScreen.classList.remove('hidden');
    setJoinLoading(false);
    elements.usernameInput.focus();
  }

  // ==========================================================================
  // WEBSOCKET MANAGEMENT
  // ==========================================================================

  /**
   * Initializes WebSocket connection to backend.
   * Target endpoint: ws://localhost:8000/ws/{username}
   */
  function connectWebSocket(username) {
    let baseUrl = elements.serverUrlInput.value.trim();
    if (!baseUrl) {
      baseUrl = 'ws://localhost:8000/ws';
    }
    // Remove trailing slashes
    baseUrl = baseUrl.replace(/\/+$/, '');

    // Form target WebSocket URL
    const wsUrl = `${baseUrl}/${encodeURIComponent(username)}`;

    hideJoinError();
    setJoinLoading(true);

    try {
      state.socket = new WebSocket(wsUrl);
    } catch (err) {
      setJoinLoading(false);
      showJoinError(`Invalid WebSocket URL: ${err.message}`);
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
        showJoinError('Could not connect to WebSocket server. Is the backend running?');
      } else {
        showChatToast('WebSocket communication error occurred');
      }
    };

    state.socket.onclose = (event) => {
      const wasConnected = state.isConnected;
      state.isConnected = false;
      state.isConnecting = false;
      state.socket = null;

      if (!wasConnected) {
        setJoinLoading(false);
        showJoinError(event.reason || 'Failed to establish WebSocket connection.');
      } else {
        updateConnectionStatus('offline', 'Disconnected');
        showChatToast('Connection lost. Please rejoin.', true);
        appendSystemNotification('Disconnected from server.', 'error-notice');
      }
    };
  }

  /**
   * Disconnects active WebSocket connection and resets state.
   */
  function disconnect(isUserInitiated = true) {
    if (state.socket) {
      // Avoid firing onclose reconnect prompts
      state.socket.onclose = null;
      state.socket.close();
      state.socket = null;
    }

    state.isConnected = false;
    state.isConnecting = false;
    state.onlineUsers = [];
    state.hasLoadedHistory = false;

    // Reset messages and users UI
    elements.messagesContainer.querySelectorAll('.message-row, .system-notification').forEach(el => el.remove());
    elements.emptyState.classList.remove('hidden');
    elements.usersList.innerHTML = '';
    elements.onlineCount.textContent = '0';

    if (isUserInitiated) {
      switchToJoinScreen();
    }
  }

  /**
   * Sends a message payload to the server in agreed client->server format:
   * {
   *   "type": "chat_message",
   *   "data": {
   *     "message": "..."
   *   }
   * }
   */
  function sendChatMessage(text) {
    if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
      showChatToast('Cannot send: Not connected to server');
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
    } catch (err) {
      console.error('Failed to send message:', err);
      showChatToast('Failed to send message to server');
    }
  }

  // ==========================================================================
  // INBOUND MESSAGE DISPATCHER
  // ==========================================================================

  /**
   * Parses and routes incoming WebSocket messages according to agreed types:
   * - chat_message
   * - user_joined
   * - user_left
   * - online_users
   * - chat_history
   * - error
   */
  function handleIncomingMessage(rawMessage) {
    let parsed;
    try {
      parsed = JSON.parse(rawMessage);
    } catch (err) {
      console.error('Failed to parse WebSocket JSON payload:', rawMessage, err);
      return;
    }

    if (!parsed || !parsed.type) {
      console.warn('Received message without type property:', parsed);
      return;
    }

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

      default:
        console.warn(`Unrecognized message type: "${type}"`, parsed);
    }
  }

  // ==========================================================================
  // MESSAGE HANDLERS
  // ==========================================================================

  /**
   * Handles incoming 'chat_message':
   * data: { message_id, username, message, timestamp }
   */
  function onChatMessageReceived(data) {
    if (!data) return;

    elements.emptyState.classList.add('hidden');

    const username = data.username || 'Anonymous';
    const message = data.message || '';
    const timestamp = data.timestamp || new Date().toISOString();
    const isSelf = username.toLowerCase() === state.currentUser.toLowerCase();

    renderChatMessage({
      messageId: data.message_id,
      username,
      message,
      timestamp,
      isSelf
    });

    scrollToBottomIfNeeded(isSelf);
  }

  /**
   * Handles 'user_joined':
   * data: { username, timestamp } or string
   */
  function onUserJoinedReceived(data) {
    const joinedUsername = (typeof data === 'string') 
      ? data 
      : (data?.username || data?.user || 'Someone');

    if (joinedUsername.toLowerCase() === state.currentUser.toLowerCase()) {
      appendSystemNotification('You joined the chat room', 'joined');
    } else {
      appendSystemNotification(`${joinedUsername} joined the chat`, 'joined');
    }

    // Add to online users if not already present
    if (!state.onlineUsers.some(u => u.toLowerCase() === joinedUsername.toLowerCase())) {
      state.onlineUsers.push(joinedUsername);
      renderOnlineUsersList();
    }

    scrollToBottomIfNeeded(false);
  }

  /**
   * Handles 'user_left':
   * data: { username, timestamp } or string
   */
  function onUserLeftReceived(data) {
    const leftUsername = (typeof data === 'string') 
      ? data 
      : (data?.username || data?.user || 'Someone');

    appendSystemNotification(`${leftUsername} left the chat`, 'left');

    // Remove from online users
    state.onlineUsers = state.onlineUsers.filter(u => u.toLowerCase() !== leftUsername.toLowerCase());
    renderOnlineUsersList();

    scrollToBottomIfNeeded(false);
  }

  /**
   * Handles 'online_users':
   * data: { users: ["Alice", "Bob"] } or array ["Alice", "Bob"]
   */
  function onOnlineUsersReceived(data) {
    let users = [];
    if (Array.isArray(data)) {
      users = data;
    } else if (data && Array.isArray(data.users)) {
      users = data.users;
    }

    // Ensure current user is in list if connected
    if (state.currentUser && !users.some(u => u.toLowerCase() === state.currentUser.toLowerCase())) {
      users.unshift(state.currentUser);
    }

    state.onlineUsers = users;
    renderOnlineUsersList();
  }

  /**
   * Handles 'chat_history':
   * data: { messages: [...] } or array [...]
   */
  function onChatHistoryReceived(data) {
    let messages = [];
    if (Array.isArray(data)) {
      messages = data;
    } else if (data && Array.isArray(data.messages)) {
      messages = data.messages;
    }

    // Clear existing message feed if re-populating history
    elements.messagesContainer.querySelectorAll('.message-row, .system-notification').forEach(el => el.remove());

    if (messages.length === 0) {
      elements.emptyState.classList.remove('hidden');
      return;
    }

    elements.emptyState.classList.add('hidden');
    appendSystemNotification('Chat history loaded', 'history-divider');

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

  /**
   * Handles 'error':
   * data: { message: "..." } or string
   */
  function onErrorReceived(data) {
    const errorMsg = (typeof data === 'string')
      ? data
      : (data?.message || data?.detail || 'An unknown error occurred on the server.');

    console.error('Server error received:', errorMsg);

    if (!state.isConnected) {
      showJoinError(errorMsg);
    } else {
      showChatToast(`Server Error: ${errorMsg}`, true);
      appendSystemNotification(`Error: ${errorMsg}`, 'error-notice');
    }
  }

  // ==========================================================================
  // DOM RENDERING
  // ==========================================================================

  /**
   * Renders a single chat message bubble into the messages container.
   */
  function renderChatMessage({ messageId, username, message, timestamp, isSelf }) {
    const row = document.createElement('div');
    row.className = `message-row ${isSelf ? 'outgoing' : 'incoming'}`;
    if (messageId) {
      row.dataset.messageId = messageId;
    }

    const timeFormatted = formatTimestamp(timestamp);
    const userColor = getUserColor(username);
    const initials = getUserInitials(username);

    // Incoming messages display sender avatar
    let avatarHtml = '';
    if (!isSelf) {
      avatarHtml = `
        <div class="avatar avatar-sm" style="background-color: ${userColor};" title="${escapeHtml(username)}">
          ${escapeHtml(initials)}
        </div>
      `;
    }

    row.innerHTML = `
      ${avatarHtml}
      <div class="message-bubble">
        <div class="message-header">
          <span class="sender-name" style="${!isSelf ? `color: ${userColor};` : ''}">
            ${escapeHtml(isSelf ? 'You' : username)}
          </span>
          <span class="message-time">${timeFormatted}</span>
        </div>
        <div class="message-text">${escapeHtml(message)}</div>
      </div>
    `;

    elements.messagesContainer.appendChild(row);
  }

  /**
   * Appends an informational system notification to the message feed.
   */
  function appendSystemNotification(text, type = 'info') {
    elements.emptyState.classList.add('hidden');

    const el = document.createElement('div');
    el.className = `system-notification ${type}`;

    let icon = 'ℹ️';
    if (type === 'joined') icon = '👋';
    else if (type === 'left') icon = '🚪';
    else if (type === 'history-divider') icon = '📜';
    else if (type === 'error-notice') icon = '⚠️';

    el.innerHTML = `<span>${icon}</span> <span>${escapeHtml(text)}</span>`;
    elements.messagesContainer.appendChild(el);
  }

  /**
   * Renders the online users list and counter.
   */
  function renderOnlineUsersList() {
    elements.usersList.innerHTML = '';
    elements.onlineCount.textContent = state.onlineUsers.length.toString();

    // Sort: Current user first, then alphabetically
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
      li.className = `user-item ${isSelf ? 'is-self' : ''}`;

      const avatarColor = getUserColor(user);
      const initials = getUserInitials(user);

      li.innerHTML = `
        <div class="user-avatar-wrap">
          <div class="avatar avatar-sm" style="background-color: ${avatarColor};">
            ${escapeHtml(initials)}
          </div>
          <span class="user-status-dot"></span>
        </div>
        <span class="user-name-text">${escapeHtml(user)}</span>
        ${isSelf ? '<span class="self-tag">You</span>' : ''}
      `;

      elements.usersList.appendChild(li);
    });
  }

  // ==========================================================================
  // SCROLL & AUTO-SCROLL MANAGEMENT
  // ==========================================================================

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
      // User is scrolled up reviewing history, show "New messages" jump button
      elements.scrollBottomBtn.classList.remove('hidden');
    }
  }

  elements.messagesContainer.addEventListener('scroll', () => {
    const container = elements.messagesContainer;
    const scrollPosition = container.scrollTop + container.clientHeight;
    const distanceToBottom = container.scrollHeight - scrollPosition;

    // Threshold of 100px to detect if user purposefully scrolled away from bottom
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
  // EVENT LISTENERS & FORM HANDLERS
  // ==========================================================================

  // Live Avatar Preview on Username Input
  elements.usernameInput.addEventListener('input', () => {
    const val = elements.usernameInput.value.trim();
    if (val) {
      const initials = getUserInitials(val);
      const color = getUserColor(val);
      if (elements.joinAvatarPreview) {
        elements.joinAvatarPreview.textContent = initials;
        elements.joinAvatarPreview.style.background = `linear-gradient(135deg, ${color}, #10b981)`;
      }
      if (elements.avatarSubText) {
        elements.avatarSubText.textContent = `Handle: @${val}`;
      }
    } else {
      if (elements.joinAvatarPreview) {
        elements.joinAvatarPreview.textContent = '?';
        elements.joinAvatarPreview.style.background = 'linear-gradient(135deg, #10b981 0%, #059669 100%)';
      }
      if (elements.avatarSubText) {
        elements.avatarSubText.textContent = 'Enter username to personalize';
      }
    }
  });

  // Handle Join Form Submit
  elements.joinForm.addEventListener('submit', (e) => {
    e.preventDefault();
    if (state.isConnecting) return;

    const rawUsername = elements.usernameInput.value.trim();
    if (!rawUsername) {
      showJoinError('Please enter a username.');
      return;
    }

    if (rawUsername.length < 2 || rawUsername.length > 25) {
      showJoinError('Username must be between 2 and 25 characters.');
      return;
    }

    // Validate alphanumeric/underscores/dashes
    if (!/^[a-zA-Z0-9_-]+$/.test(rawUsername)) {
      showJoinError('Username can only contain letters, numbers, hyphens, and underscores.');
      return;
    }

    state.currentUser = rawUsername;
    connectWebSocket(rawUsername);
  });

  // Handle Message Input & Send Form Submit
  elements.messageForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = elements.messageInput.value.trim();
    if (!text) return;

    sendChatMessage(text);
    elements.messageInput.value = '';
    elements.messageInput.focus();
  });

  // Allow Enter key to submit cleanly
  elements.messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      elements.messageForm.dispatchEvent(new Event('submit', { cancelable: true }));
    }
  });

  // Leave / Disconnect button
  elements.leaveBtn.addEventListener('click', () => {
    if (confirm('Are you sure you want to leave the chat?')) {
      disconnect(true);
    }
  });

  // Mobile sidebar toggle
  elements.toggleSidebarBtn.addEventListener('click', () => {
    elements.sidebar.classList.toggle('open');
    elements.sidebarOverlay.classList.toggle('hidden');
  });

  elements.sidebarOverlay.addEventListener('click', () => {
    elements.sidebar.classList.remove('open');
    elements.sidebarOverlay.classList.add('hidden');
  });

  // Handle browser tab close or reload
  window.addEventListener('beforeunload', () => {
    if (state.socket) {
      state.socket.close();
    }
  });

})();
