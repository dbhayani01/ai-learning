/* ── Auth Management ───────────────────────────────────────────────────────── */
let authToken = localStorage.getItem('chat_auth_token');
let activeSessionId = null;
let isSignupMode = false;

function setAuthToken(token) {
  authToken = token;
  if (token) {
    localStorage.setItem('chat_auth_token', token);
  } else {
    localStorage.removeItem('chat_auth_token');
  }
}

function toggleAuthMode() {
  isSignupMode = !isSignupMode;
  document.getElementById('auth-title').textContent = isSignupMode ? 'Create Account' : 'Welcome Back';
  document.getElementById('auth-subtitle').textContent = isSignupMode ? 'Sign up to save your chats.' : 'Log in to access your chat history.';
  document.getElementById('btn-auth-submit').textContent = isSignupMode ? 'Sign Up' : 'Log In';
  document.getElementById('auth-switch-text').textContent = isSignupMode ? 'Already have an account?' : "Don't have an account?";
  document.getElementById('auth-switch-link').textContent = isSignupMode ? 'Log in' : 'Sign up';
  document.getElementById('auth-error').classList.add('hidden');
}

async function submitAuth() {
  const user = document.getElementById('auth-username').value.trim();
  const pass = document.getElementById('auth-password').value.trim();
  const errEl = document.getElementById('auth-error');
  
  if (!user || !pass) {
    errEl.textContent = "Please enter username and password.";
    errEl.classList.remove('hidden');
    return;
  }
  
  const endpoint = isSignupMode ? '/signup' : '/login';
  
  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user, password: pass })
    });
    
    const data = await res.json();
    if (!res.ok) {
      errEl.textContent = data.detail || "Authentication failed.";
      errEl.classList.remove('hidden');
      return;
    }
    
    setAuthToken(data.token);
    document.getElementById('auth-overlay').classList.add('hidden');
    
    // Update Header & Sidebar
    if (data.role === 'guest') {
      document.getElementById('user-greeting').textContent = 'Hi, Guest';
      document.getElementById('guest-banner').style.display = 'block';
    } else {
      document.getElementById('user-greeting').textContent = `Hi, ${data.username}`;
      document.getElementById('guest-banner').style.display = 'none';
    }
    
    document.getElementById('user-greeting').style.display = 'inline';
    document.getElementById('btn-logout').style.display = 'inline';
    document.getElementById('sidebar').style.display = 'flex';
    document.getElementById('btn-floating-toggle').style.display = 'none';
    
    startNewChat();
    loadSessions();
    loadDocuments();
    
  } catch (err) {
    errEl.textContent = "Network error. Server may be down.";
    errEl.classList.remove('hidden');
  }
}

async function logout() {
  if (authToken) {
    await fetch('/logout', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${authToken}` }
    }).catch(()=>{});
  }
  setAuthToken(null);
  activeSessionId = null;
  document.getElementById('chat-history').innerHTML = `
    <div class="chat-message ai-message">
      <div class="message-content">
        <p>Hello! I am your RAG Knowledge Assistant. Please upload a document to get started.</p>
      </div>
    </div>
  `;
  document.getElementById('user-greeting').style.display = 'none';
  document.getElementById('btn-logout').style.display = 'none';
  document.getElementById('sidebar').style.display = 'none';
  document.getElementById('btn-floating-toggle').style.display = 'none';
  
  // Transition seamlessly to a new guest session
  checkAuthOnLoad();
}

async function checkAuthOnLoad() {
  if (!authToken) {
    // Generate guest token
    try {
      const res = await fetch('/guest', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setAuthToken(data.token);
        // Refresh with new token
        verifyCurrentToken();
      } else {
        document.getElementById('auth-overlay').classList.remove('hidden');
      }
    } catch(e) {
      document.getElementById('auth-overlay').classList.remove('hidden');
    }
    return;
  }
  verifyCurrentToken();
}

async function verifyCurrentToken() {
  try {
    const res = await fetch('/me', {
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    
    if (res.ok) {
      const data = await res.json();
      document.getElementById('auth-overlay').classList.add('hidden');
      
      if (data.role === 'guest') {
        document.getElementById('user-greeting').textContent = 'Hi, Guest';
        document.getElementById('guest-banner').style.display = 'block';
        document.getElementById('btn-logout').style.display = 'none';
      } else {
        document.getElementById('user-greeting').textContent = `Hi, ${data.username}`;
        document.getElementById('guest-banner').style.display = 'none';
        document.getElementById('btn-logout').style.display = 'inline';
      }
      
      document.getElementById('user-greeting').style.display = 'inline';
      document.getElementById('sidebar').style.display = 'flex';
      document.getElementById('btn-floating-toggle').style.display = 'none';
      startNewChat();
      loadSessions();
      loadDocuments();
    } else {
      // Token invalid, clear it and try guest mode again
      setAuthToken(null);
      checkAuthOnLoad();
    }
  } catch (err) {
    console.error("Auth check failed:", err);
  }
}

/* ── Sessions & History ──────────────────────────────────────────────────── */
async function loadSessions() {
  if (!authToken) return;
  try {
    const res = await fetch(`/sessions`, { headers: { 'Authorization': `Bearer ${authToken}` } });
    if (!res.ok) return;
    const data = await res.json();
    const list = document.getElementById('session-list');
    list.innerHTML = '';
    
    data.sessions.forEach(session => {
      const el = document.createElement('div');
      el.className = `session-item ${session.id === activeSessionId ? 'active' : ''}`;
      el.innerHTML = `
        <span>${session.title}</span>
        <button class="session-delete" onclick="deleteSession('${session.id}', event)">×</button>
      `;
      el.onclick = () => loadHistory(session.id);
      list.appendChild(el);
    });
  } catch (e) {
    console.error("Failed to load sessions", e);
  }
}

async function loadDocuments() {
  if (!authToken) return;
  try {
    const res = await fetch(`/documents`, { headers: { 'Authorization': `Bearer ${authToken}` } });
    if (!res.ok) return;
    const data = await res.json();
    
    // Update limits display
    const limitsEl = document.getElementById('doc-limits-display');
    if (limitsEl) limitsEl.textContent = `${data.usage} / ${data.limit}`;
    
    const list = document.getElementById('document-list');
    if (!list) return;
    list.innerHTML = '';
    
    data.documents.forEach(filename => {
      const el = document.createElement('div');
      el.className = 'session-item';
      // Truncate name for UI
      const shortName = filename.length > 22 ? filename.substring(0, 22) + "..." : filename;
      el.innerHTML = `
        <span title="${filename}">📄 ${shortName}</span>
        <button class="session-delete" onclick="deleteDocument('${filename}', event)">🗑</button>
      `;
      list.appendChild(el);
    });
  } catch (e) {
    console.error("Failed to load documents", e);
  }
}

async function deleteDocument(filename, event) {
  if (event) event.stopPropagation();
  if (!confirm(`Are you sure you want to delete ${filename}? This will remove it from the AI's knowledge.`)) return;
  
  if (!authToken) return;
  try {
    const res = await fetch(`/documents/${filename}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    if (res.ok) {
      loadDocuments();
    } else {
      alert("Failed to delete document.");
    }
  } catch (e) {
    console.error(e);
  }
}

function startNewChat() {
  activeSessionId = null;
  document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
  document.getElementById('chat-history').innerHTML = `
    <div class="chat-message ai-message">
      <div class="message-content">
        <p>Hello! Ask me a question and a new chat session will begin.</p>
      </div>
    </div>
  `;
}

async function loadHistory(sessionId) {
  if (!authToken) return;
  activeSessionId = sessionId;
  
  // Highlight active
  loadSessions(); // Re-render to highlight active
  
  try {
    const res = await fetch(`/history?session_id=${sessionId}`, {
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    if (!res.ok) return;
    const data = await res.json();
    
    const historyEl = document.getElementById('chat-history');
    historyEl.innerHTML = '';
    
    if (data.messages && data.messages.length > 0) {
      data.messages.forEach(msg => {
        addMessage(msg.content, msg.role, msg.metadata);
      });
    } else {
      startNewChat();
    }
  } catch (err) {
    console.error("Failed to load history:", err);
  }
}

document.addEventListener('DOMContentLoaded', checkAuthOnLoad);

/* ── File Upload ──────────────────────────────────────────────────────────── */
const fileInput = document.getElementById('pdfFile');

fileInput.addEventListener('change', () => {
  if (fileInput.files.length > 0) {
    uploadFile();
  }
});

async function uploadFile() {
  const file = fileInput.files[0];
  if (!file) return;

  // Reset file input so same file can be uploaded again if needed
  fileInput.value = '';

  const formData = new FormData();
  formData.append('file', file);

  showToast(file.name, 'Uploading...');

  try {
    const res = await fetch('/upload', { 
      method: 'POST', 
      headers: { 'Authorization': `Bearer ${authToken}` },
      body: formData 
    });
    const data = await res.json();

    if (!res.ok) {
      updateToastError(data.detail || 'Upload failed');
      return;
    }

    pollJob(data.job_id);

  } catch (err) {
    updateToastError('Network error — could not reach the server.');
  }
}

/* ── Polling ─────────────────────────────────────────────────────────────── */
function pollJob(jobId) {
  const INTERVAL = 1500;
  const MAX_POLLS = 40;
  let polls = 0;

  const tick = async () => {
    try {
      const res = await fetch(`/job/${jobId}`);
      if (!res.ok) throw new Error('Poll failed');
      const data = await res.json();

      if (data.status === 'processing') {
        updateToastProgress('Processing document...', 50);
      }

      if (data.status === 'completed') {
        updateToastSuccess(`✓ ${data.pages} pages · ${data.chunks} chunks added`);
        return; // stop polling
      }

      if (data.status === 'failed') {
        updateToastError(`✗ ${data.error || 'Unknown error'}`);
        return; // stop polling
      }

      if (++polls < MAX_POLLS) setTimeout(tick, INTERVAL);

    } catch (_) {
      if (++polls < MAX_POLLS) setTimeout(tick, INTERVAL);
    }
  };

  setTimeout(tick, INTERVAL);
}

/* ── Toast UI ────────────────────────────────────────────────────────────── */
function showToast(filename, status) {
  const toast = document.getElementById('upload-toast');
  document.getElementById('job-filename').textContent = filename;
  document.getElementById('job-meta').textContent = status;
  document.getElementById('job-meta').style.color = 'var(--text-3)';
  document.getElementById('progress-fill').style.width = '10%';
  document.getElementById('progress-fill').style.background = 'var(--accent)';
  document.getElementById('toast-spinner').classList.remove('hidden');
  toast.classList.remove('hidden');
}

function updateToastProgress(status, percent) {
  document.getElementById('job-meta').textContent = status;
  document.getElementById('progress-fill').style.width = percent + '%';
}

function updateToastSuccess(status) {
  document.getElementById('job-meta').textContent = status;
  document.getElementById('job-meta').style.color = 'var(--green)';
  document.getElementById('progress-fill').style.width = '100%';
  document.getElementById('progress-fill').style.background = 'var(--green)';
  document.getElementById('toast-spinner').classList.add('hidden');
  loadDocuments(); // Refresh limits and doc list
  setTimeout(() => {
    document.getElementById('upload-toast').classList.add('hidden');
  }, 4000);
}

function updateToastError(error) {
  document.getElementById('job-meta').textContent = error;
  document.getElementById('job-meta').style.color = 'var(--red)';
  document.getElementById('progress-fill').style.width = '100%';
  document.getElementById('progress-fill').style.background = 'var(--red)';
  document.getElementById('toast-spinner').classList.add('hidden');
  setTimeout(() => {
    document.getElementById('upload-toast').classList.add('hidden');
  }, 5000);
}

/* ── Ask ──────────────────────────────────────────────────────────────────── */
function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    askQuestion();
  }
}

async function askQuestion() {
  const inputEl = document.getElementById('question');
  const q = inputEl.value.trim();
  if (!q) {
    inputEl.focus();
    return;
  }

  // Clear input
  inputEl.value = '';
  inputEl.style.height = 'auto'; // reset height
  const btn = document.getElementById('btn-send');
  btn.disabled = true;

  // Add user message to UI
  addMessage(q, 'user');

  // Create empty AI message container for streaming
  const msgContainer = addMessage('', 'ai');

  try {
    const res  = await fetch('/ask', {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({ question: q, session_id: activeSessionId }),
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      if (res.status === 403 && errData.detail && errData.detail.includes("LIMIT_REACHED")) {
        msgContainer.textContent = "You've reached the free limits! Please sign up to continue.";
      } else {
        if (typeof errData.detail === 'object') {
          msgContainer.textContent = JSON.stringify(errData.detail);
        } else {
          msgContainer.textContent = errData.detail || 'Request failed.';
        }
      }
      msgContainer.style.color = 'var(--red)';
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    // Smooth typewriter queue
    let tokenQueue = [];
    let isTyping = false;
    
    function processQueue() {
      if (tokenQueue.length === 0) {
        isTyping = false;
        return;
      }
      isTyping = true;
      msgContainer.textContent += tokenQueue.shift();
      scrollToBottom();
      // Groq is fast, so we add a slight artificial delay per token for the typing effect
      setTimeout(processQueue, 15);
    }

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      
      const lines = buffer.split('\n\n');
      buffer = lines.pop(); 
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.substring(6));
            if (data.type === 'session_id') {
              const isNewSession = !activeSessionId;
              activeSessionId = data.session_id;
              if (isNewSession) loadSessions(); // Refresh list to show new chat
            } else if (data.type === 'metadata') {
              // Add sources button to the message wrapper
              renderMetadata(msgContainer.parentElement, data.chunks);
            } else if (data.type === 'token') {
              for (const char of data.content) {
                tokenQueue.push(char);
              }
              if (!isTyping) processQueue();
            } else if (data.type === 'error') {
              msgContainer.textContent += '\n\n[Error: ' + data.content + ']';
            }
          } catch(e) {
            console.error(e);
          }
        }
      }
    }
  } catch (err) {
    msgContainer.textContent = 'Network error — could not reach the server.';
    msgContainer.style.color = 'var(--red)';
  } finally {
    btn.disabled = false;
  }
}

function addMessage(text, sender, metadata = null) {
  const history = document.getElementById('chat-history');
  
  const wrap = document.createElement('div');
  wrap.className = `chat-message ${sender}-message`;
  
  const content = document.createElement('div');
  content.className = 'message-content';
  content.textContent = text;
  
  wrap.appendChild(content);
  
  // Attach metadata tags if provided
  if (metadata && metadata.length > 0 && sender === 'ai') {
    renderMetadata(wrap, metadata);
  }
  
  history.appendChild(wrap);
  
  scrollToBottom();
  
  return content;
}

function renderMetadata(wrap, metadata) {
  if (!metadata || metadata.length === 0) return;

  const metaContainer = document.createElement('div');
  metaContainer.className = 'sources-container';
  metaContainer.style.display = 'none'; // hidden initially

  // Extract unique source filenames and check if deleted
  const uniqueSourcesMap = {};
  metadata.forEach(m => {
    const sName = m.source.split(/[\/\\]/).pop();
    if (!uniqueSourcesMap[sName]) uniqueSourcesMap[sName] = { deleted: m.is_deleted };
    else if (m.is_deleted) uniqueSourcesMap[sName].deleted = true;
  });

  const escapeHtml = (unsafe) => {
    return String(unsafe)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  };

  Object.keys(uniqueSourcesMap).forEach(sourceName => {
    const isDeleted = uniqueSourcesMap[sourceName].deleted;
    const safeSource = escapeHtml(sourceName);
    const tag = document.createElement('span');
    tag.className = 'source-tag';
    
    if (isDeleted) {
      tag.innerHTML = `📄 <s style="opacity: 0.6;">${safeSource}</s> <span style="color: var(--red); font-weight: 500; font-size: 0.7rem; margin-left: 4px;">(Deleted)</span>`;
      tag.title = "Source document was deleted";
      tag.style.border = "1px solid rgba(239, 68, 68, 0.2)";
    } else {
      tag.innerHTML = `📄 ${safeSource}`;
    }
    
    metaContainer.appendChild(tag);
  });

  const toggleBtn = document.createElement('button');
  toggleBtn.className = 'btn-ghost source-toggle-btn';
  toggleBtn.textContent = 'View Sources';
  toggleBtn.style.marginTop = '8px';
  toggleBtn.onclick = () => {
    if (metaContainer.style.display === 'none') {
      metaContainer.style.display = 'flex';
      toggleBtn.textContent = 'Hide Sources';
    } else {
      metaContainer.style.display = 'none';
      toggleBtn.textContent = 'View Sources';
    }
  };

  wrap.appendChild(toggleBtn);
  wrap.appendChild(metaContainer);
}

function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const floatingToggle = document.getElementById('btn-floating-toggle');
  if (sidebar.style.display === 'none' || sidebar.style.display === '') {
    sidebar.style.display = 'flex';
    floatingToggle.style.display = 'none';
  } else {
    sidebar.style.display = 'none';
    floatingToggle.style.display = 'inline-block';
  }
}

function scrollToBottom() {
  const history = document.getElementById('chat-history');
  history.scrollTop = history.scrollHeight;
}

async function deleteSession(sessionId, event) {
  event.stopPropagation();
  try {
    await fetch(`/history?session_id=${sessionId}`, { 
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    if (activeSessionId === sessionId) {
      startNewChat();
    }
    loadSessions();
  } catch (err) {
    console.error("Failed to delete chat:", err);
  }
}

function clearChat() {
  if (activeSessionId) {
    deleteSession(activeSessionId, { stopPropagation: ()=>{} });
  } else {
    startNewChat();
  }
}
