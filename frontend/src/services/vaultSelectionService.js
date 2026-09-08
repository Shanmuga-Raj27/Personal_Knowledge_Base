import { isIndexed } from './ragService'

/**
 * Partition a list of documents into those that need RAG indexing
 * and those already indexed.
 * Pure function — no network, no React.
 * @param {Array<object>} docs
 * @returns {{ toIndex: Array<object>, alreadyIndexed: Array<object> }}
 */
export function partitionForKnowledgeBase(docs) {
  const toIndex = []
  const alreadyIndexed = []
  for (const doc of docs || []) {
    if (isIndexed(doc)) {
      alreadyIndexed.push(doc)
    } else {
      toIndex.push(doc)
    }
  }
  return { toIndex, alreadyIndexed }
}
