/* ── Session Management ────────────────────────────────────────────────────── */
function getSessionId() {
  let sid = sessionStorage.getItem('chat_session_id');
  if (!sid) {
    sid = 'sess_' + Math.random().toString(36).substr(2, 9);
    sessionStorage.setItem('chat_session_id', sid);
  }
  return sid;
}

const sessionId = getSessionId();

/* ── Load History ────────────────────────────────────────────────────────── */
async function loadHistory() {
  try {
    const res = await fetch(`/history/${sessionId}`);
    if (!res.ok) return;
    const data = await res.json();
    
    if (data.messages && data.messages.length > 0) {
      // Clear the welcome message
      const historyEl = document.getElementById('chat-history');
      historyEl.innerHTML = '';
      
      // Render history
      data.messages.forEach(msg => {
        addMessage(msg.content, msg.role);
      });
    }
  } catch (err) {
    console.error("Failed to load history:", err);
  }
}

document.addEventListener('DOMContentLoaded', loadHistory);

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
    const res = await fetch('/upload', { method: 'POST', body: formData });
    const data = await res.json();

    if (!res.ok) {
      updateToastError(data.detail || 'Upload failed.');
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
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, session_id: sessionId }),
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      msgContainer.textContent = errData.detail || 'Request failed.';
      msgContainer.style.color = 'var(--red)';
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

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
            if (data.type === 'token') {
              msgContainer.textContent += data.content;
              scrollToBottom();
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

function addMessage(text, sender) {
  const history = document.getElementById('chat-history');
  
  const wrap = document.createElement('div');
  wrap.className = `chat-message ${sender}-message`;
  
  const content = document.createElement('div');
  content.className = 'message-content';
  content.textContent = text;
  
  wrap.appendChild(content);
  history.appendChild(wrap);
  
  scrollToBottom();
  
  return content; // Return the content node so we can stream into it if it's an AI message
}

function scrollToBottom() {
  const history = document.getElementById('chat-history');
  history.scrollTop = history.scrollHeight;
}

async function clearChat() {
  try {
    await fetch(`/history/${sessionId}`, { method: 'DELETE' });
    const historyEl = document.getElementById('chat-history');
    historyEl.innerHTML = `
      <div class="chat-message ai-message">
        <div class="message-content">
          <p>Chat history cleared. How can I help you today?</p>
        </div>
      </div>
    `;
  } catch (err) {
    console.error("Failed to clear chat:", err);
  }
}
