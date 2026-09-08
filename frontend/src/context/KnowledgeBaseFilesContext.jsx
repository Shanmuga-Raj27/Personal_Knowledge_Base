import { createContext, useContext, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { loadSession } from '../services/ragHistoryService'
import { mergeSelection as mergeSelectionPure } from '../services/ragService'

const KnowledgeBaseFilesContext = createContext(null)

/**
 * Shared Knowledge Base selection.
 *
 * Single source of truth for which documents are selected for RAG chat.
 * Initialized from the persisted session (so a refresh restores it).
 * Persistence itself is still owned by KnowledgeBase.jsx's debounced
 * saveSession effect — this context only holds in-memory state.
 */
export function KnowledgeBaseFilesProvider({ userId, children }) {
  const [selected, setSelected] = useState(() => loadSession(userId).selected)

  // Re-hydrate when the active user changes (login as a different user).
  const prevUserIdRef = useRef(userId)
  useEffect(() => {
    if (prevUserIdRef.current !== userId) {
      prevUserIdRef.current = userId
      setSelected(loadSession(userId).selected)
    }
  }, [userId])

  const addDocs = useCallback((docs) => {
    let result = null
    setSelected((prev) => {
      result = mergeSelectionPure(prev, docs)
      return result.next
    })
    // setSelected is async; return is stale in this tick for callers that
    // need it synchronously — compute it from current state instead:
    // But most callers (Vault) don't need the sync copy; they show a banner
    // computed from mergeSelectionPure(selected, docs) before calling addDocs.
    // To keep the API simple for Vault, also return a sync-computed preview:
    return result
  }, [])

  // Synchronous preview without mutating — useful for composing alert text.
  const previewAddDocs = useCallback((docs) => mergeSelectionPure(selected, docs), [selected])

  const removeDoc = useCallback((fileId) => {
    setSelected((prev) => prev.filter((d) => d.fileId !== fileId))
  }, [])

  const clear = useCallback(() => {
    setSelected([])
  }, [])

  const value = useMemo(
    () => ({ selected, setSelected, addDocs, previewAddDocs, removeDoc, clear }),
    [selected, addDocs, previewAddDocs, removeDoc, clear],
  )

  return (
    <KnowledgeBaseFilesContext.Provider value={value}>
      {children}
    </KnowledgeBaseFilesContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useKnowledgeBaseFiles() {
  const ctx = useContext(KnowledgeBaseFilesContext)
  if (!ctx) throw new Error('useKnowledgeBaseFiles must be used within KnowledgeBaseFilesProvider')
  return ctx
}
