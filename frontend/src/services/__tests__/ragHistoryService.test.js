import { describe, it, expect, beforeEach } from 'vitest'
import {
  saveSession,
  loadSession,
  clearSession,
} from '../ragHistoryService'

/**
 * Unit tests for the RAG session persistence layer.
 * localStorage is stubbed in-memory because vitest runs in the node
 * environment (no jsdom). These pin the guarantees the UI relies on:
 *   - round-trip save/load of messages + selected docs
 *   - user-scoped keys (one user never sees another's session)
 *   - graceful degradation on corrupt / disabled storage
 *   - streaming flags are normalized to false on restore
 */

const store = new Map()

const stubLocalStorage = () => {
  globalThis.localStorage = {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
    clear: () => store.clear(),
  }
}

const makeDoc = (fileId, overrides = {}) => ({
  fileId,
  filename: `report-${fileId}.pdf`,
  title: `Report ${fileId}`,
  contentType: 'application/pdf',
  indexingStatus: 'INDEXED',
  ...overrides,
})

beforeEach(() => {
  store.clear()
  stubLocalStorage()
})

describe('saveSession / loadSession round-trip', () => {
  it('persists messages and selected docs and restores them intact', () => {
    const messages = [
      { role: 'user', text: 'Summarize the Q3 report?' },
      { role: 'assistant', text: '**Key takeaways:** revenue grew.\n\n- list item', sources: [{ filename: 'report.pdf', page_start: 1, page_end: 2 }], diagnostics: { insufficient_evidence: false } },
    ]
    const selected = [makeDoc(3), makeDoc(7)]

    saveSession(11, { messages, selected })

    const restored = loadSession(11)
    expect(restored.messages).toEqual([
      expect.objectContaining({ role: 'user', text: 'Summarize the Q3 report?' }),
      expect.objectContaining({
        role: 'assistant',
        text: '**Key takeaways:** revenue grew.\n\n- list item',
        sources: [{ filename: 'report.pdf', page_start: 1, page_end: 2 }],
      }),
    ])
    expect(restored.selected).toHaveLength(2)
    expect(restored.selected[0].fileId).toBe(3)
    expect(restored.selected[1].fileId).toBe(7)
  })

  it('scopes storage per user (no cross-user leakage)', () => {
    saveSession(1, { messages: [{ role: 'user', text: 'user one' }], selected: [makeDoc(1)] })
    saveSession(2, { messages: [{ role: 'user', text: 'user two' }], selected: [makeDoc(2)] })

    expect(loadSession(1).messages[0].text).toBe('user one')
    expect(loadSession(2).messages[0].text).toBe('user two')
    expect(loadSession(2).messages).not.toEqual(loadSession(1).messages)
  })
})

describe('normalization on restore', () => {
  it('forces streaming to false on restored messages', () => {
    saveSession(5, { messages: [{ role: 'assistant', text: 'partial', streaming: true, sources: [], diagnostics: {} }], selected: [] })
    const restored = loadSession(5)
    expect(restored.messages[0]).toEqual(
      expect.objectContaining({ text: 'partial', streaming: false }),
    )
  })

  it('drops malformed message entries instead of trusting them', () => {
    store.set('pkb_rag_5', JSON.stringify({
      messages: [null, 'garbage', { role: 'robot', text: 123 }, { role: 'user', text: 'ok' }, { noText: true }],
      selected: [null, 'x', { fileId: 9 }, { fileId: 'bad', filename: 'nope.pdf' }],
    }))
    const restored = loadSession(5)
    expect(restored.messages).toEqual([expect.objectContaining({ role: 'user', text: 'ok' })])
    expect(restored.selected).toEqual([expect.objectContaining({ fileId: 9 })])
  })

  it('caps the saved messages to the MAX limit', () => {
    const many = Array.from({ length: 250 }, (_, i) => ({ role: 'user', text: `q${i}` }))
    saveSession(5, { messages: many, selected: [] })
    const restored = loadSession(5)
    expect(restored.messages).toHaveLength(200)
  })
})

describe('robustness', () => {
  it('returns an empty session when nothing is stored', () => {
    expect(loadSession(999)).toEqual({ messages: [], selected: [] })
  })

  it('degrades gracefully on corrupt stored JSON', () => {
    store.set('pkb_rag_5', '{not valid json')
    expect(loadSession(5)).toEqual({ messages: [], selected: [] })
  })

  it('does not throw when storage itself is unavailable', () => {
    globalThis.localStorage = {
      getItem: () => { throw new Error('denied') },
      setItem: () => { throw new Error('denied') },
      removeItem: () => { throw new Error('denied') },
    }
    expect(() => saveSession(5, { messages: [{ role: 'user', text: 'x' }], selected: [] })).not.toThrow()
    expect(loadSession(5)).toEqual({ messages: [], selected: [] })
  })

  it('clears only the target user session', () => {
    saveSession(1, { messages: [{ role: 'user', text: 'a' }], selected: [] })
    saveSession(2, { messages: [{ role: 'user', text: 'b' }], selected: [] })
    clearSession(1)
    expect(loadSession(1).messages).toEqual([])
    expect(loadSession(2).messages).toEqual([expect.objectContaining({ text: 'b' })])
  })
})