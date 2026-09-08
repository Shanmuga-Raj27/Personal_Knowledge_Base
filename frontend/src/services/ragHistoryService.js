/**
 * frontend/src/services/ragHistoryService.js
 *
 * Per-user RAG session persistence backed by localStorage.
 *
 * Stores the conversation (messages + selected documents) under a
 * user-scoped key so history survives tab switches (keep-mounted also
 * preserves it in memory) AND full browser refreshes. Nothing here
 * touches the network — this is intentionally a lightweight local
 * persistence layer; server-side history is a separate, larger feature.
 *
 * Guard rails:
 *  - Storage read failures (quota / tampered JSON / disabled storage)
 *    degrade gracefully to an empty session.
 *  - Loaded data is validated to a known safe shape; malformed entries
 *    are dropped rather than trusted.
 *  - Writes are capped so a long conversation cannot blow the ~5MB quota.
 */

const STORAGE_PREFIX = 'pkb_rag_'
const MAX_MESSAGES = 200
const MAX_SELECTED = 5
const MAX_MESSAGE_CHARS = 50000

function storageKey(userId) {
  return `${STORAGE_PREFIX}${userId}`
}

function toSafeMessage(msg) {
  if (!msg || typeof msg !== 'object') return null
  if (msg.role !== 'user' && msg.role !== 'assistant') return null
  if (typeof msg.text !== 'string') return null
  const text = msg.text.slice(0, MAX_MESSAGE_CHARS)
  const sources = Array.isArray(msg.sources)
    ? msg.sources.slice(0, 20).map((s) => (s && typeof s === 'object') ? s : null).filter(Boolean)
    : []
  const hasDiag = Boolean(msg.diagnostics) && typeof msg.diagnostics === 'object'
  return {
    role: msg.role,
    text,
    sources,
    diagnostics: hasDiag ? msg.diagnostics : {},
    ...(msg.error ? { error: String(msg.error) } : {}),
    streaming: false,
  }
}

function toSafeDoc(doc) {
  if (!doc || typeof doc !== 'object' || typeof doc.fileId !== 'number') return null
  return {
    fileId: doc.fileId,
    filename: typeof doc.filename === 'string' ? doc.filename : '',
    title: typeof doc.title === 'string' ? doc.title : '',
    contentType: typeof doc.contentType === 'string' ? doc.contentType : '',
    indexingStatus: typeof doc.indexingStatus === 'string' ? doc.indexingStatus : 'INDEXED',
  }
}

/**
 * Persist the current conversation for a user.
 * @param {number|string} userId
 * @param {{ messages: Array<object>, selected: Array<object> }} session
 */
export function saveSession(userId, { messages, selected }) {
  if (userId == null) return
  try {
    const safeMessages = Array.isArray(messages)
      ? messages.map(toSafeMessage).filter(Boolean).slice(-MAX_MESSAGES)
      : []
    const safeSelected = Array.isArray(selected)
      ? selected.map(toSafeDoc).filter(Boolean).slice(0, MAX_SELECTED)
      : []
    const payload = { messages: safeMessages, selected: safeSelected, updatedAt: Date.now() }
    localStorage.setItem(storageKey(userId), JSON.stringify(payload))
  } catch (err) {
    // Quota exceeded or disabled storage — never throw into the UI.
    console.warn('[ragHistoryService] Failed to save session:', err)
  }
}

/**
 * Restore the saved conversation for a user.
 * @param {number|string} userId
 * @returns {{ messages: Array<object>, selected: Array<object> }} Safe, validated session.
 */
export function loadSession(userId) {
  if (userId == null) return { messages: [], selected: [] }
  try {
    const raw = localStorage.getItem(storageKey(userId))
    if (!raw) return { messages: [], selected: [] }
    const parsed = JSON.parse(raw)
    const messages = Array.isArray(parsed.messages)
      ? parsed.messages.map(toSafeMessage).filter(Boolean)
      : []
    const selected = Array.isArray(parsed.selected)
      ? parsed.selected.map(toSafeDoc).filter(Boolean).slice(0, MAX_SELECTED)
      : []
    return { messages, selected }
  } catch (err) {
    console.warn('[ragHistoryService] Failed to load session:', err)
    return { messages: [], selected: [] }
  }
}

/**
 * Delete the saved conversation for a user.
 * @param {number|string} userId
 */
export function clearSession(userId) {
  if (userId == null) return
  try {
    localStorage.removeItem(storageKey(userId))
  } catch (err) {
    console.warn('[ragHistoryService] Failed to clear session:', err)
  }
}