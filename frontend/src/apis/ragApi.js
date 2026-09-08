import axiosClient from './axiosClient'

/**
 * frontend/src/apis/ragApi.js
 *
 * Phase 8 RAG network client. Speaks ONLY the SSE wire contract exposed by
 * POST /rag/query (Phase 6):
 *
 *     : connected\n\n                                              <- comment, ignore
 *     data: {"type":"token","text":"..."}\n\n                      <- answer token
 *     data: {"type":"final","sources":[...],"diagnostics":{...}}\n\n <- answer complete
 *     data: {"type":"error","detail":"..."}\n\n                    <- mid-stream failure
 *
 * Layer rules (Phase 8 §5.1): this file contains network + SSE framing only.
 * No React state, no business rules, no JSX. The pure `parseRagSse` parser is
 * exported separately so Step 5 / Step 7 can unit-test it in isolation.
 */

/**
 * Parse a raw SSE response body into a RAG answer object.
 * Pure function: no network, no React, deterministic on `body`.
 *
 * @param {string} body Raw text received from POST /rag/query
 * @returns {{ answer: string, sources: Array<object>, diagnostics: object, error?: string }}
 */
export function parseRagSse(body) {
  const result = {
    answer: '',
    sources: [],
    diagnostics: {},
  }

  const lines = String(body).split(/\r?\n/)

  for (const line of lines) {
    if (!line.startsWith('data: ')) continue

    const payloadJson = line.slice('data: '.length).trim()
    if (!payloadJson) continue

    let event
    try {
      event = JSON.parse(payloadJson)
    } catch {
      // Malformed line: skip without throwing (Phase 8 §8.2 tolerance).
      continue
    }

    if (event.type === 'token') {
      if (typeof event.text === 'string') {
        result.answer += event.text
      }
    } else if (event.type === 'final') {
      result.sources = Array.isArray(event.sources) ? event.sources : []
      result.diagnostics = event.diagnostics && typeof event.diagnostics === 'object'
        ? event.diagnostics
        : {}
    } else if (event.type === 'error') {
      result.error = event.detail || 'Answer generation failed mid-stream.'
    }
  }

  return result
}

/**
 * Stream a RAG answer from POST /rag/query over SSE.
 *
 * Uses axios with `responseType: 'text'` and a 60s timeout. The axiosClient
 * response interceptor unwraps `response.data`, which for a text response is
 * the raw SSE body. We then parse it line-by-line and drive `onToken` with the
 * progressively-accumulated answer so the UI can re-render as parsing proceeds.
 * The outer promise resolves once the full body has been consumed.
 *
 * This is the documented fire-and-forget MVP (Phase 8 §5.2): rendering happens
 * progressively as line parsing advances. Genuine incremental per-chunk network
 * streaming would require fetch() + a ReadableStream reader; not needed here.
 *
 * @param {{ question: string, file_ids?: number[], top_k?: number, score_threshold?: number }} payload
 * @param {(text: string) => void} onToken Called with each accumulated answer text.
 * @param {AbortSignal} [signal] Optional AbortSignal to cancel the request.
 * @returns {Promise<{ answer: string, sources: Array<object>, diagnostics: object, error?: string }>}
 */
export async function streamRagQuery(payload, onToken, signal) {
  const response = await axiosClient.post('/rag/query', payload, {
    responseType: 'text',
    timeout: 60000,
    signal,
  })

  const body = String(response)

  // Parse the full body while driving the live-update callback progressively.
  const events = parseSseEvents(body)
  let answer = ''
  let sources = []
  let diagnostics = {}
  let error

  for (const event of events) {
    if (event.type === 'token' && typeof event.text === 'string') {
      answer += event.text
      if (typeof onToken === 'function') onToken(answer)
    } else if (event.type === 'final') {
      sources = Array.isArray(event.sources) ? event.sources : []
      diagnostics = event.diagnostics && typeof event.diagnostics === 'object'
        ? event.diagnostics
        : {}
    } else if (event.type === 'error') {
      error = event.detail || 'Answer generation failed mid-stream.'
    }
  }

  return { answer, sources, diagnostics, ...(error ? { error } : {}) }
}

/**
 * Split raw SSE text into an array of parsed event objects.
 * Shared by parseRagSse and streamRagQuery so parsing is a single source of
 * truth; tolerant of comment lines (": connected"), blank lines, and bad JSON.
 *
 * @param {string} body Raw SSE response body.
 * @returns {Array<object>}
 */
export function parseSseEvents(body) {
  const events = []
  const lines = String(body).split(/\r?\n/)

  for (const line of lines) {
    if (!line.startsWith('data: ')) continue

    const payloadJson = line.slice('data: '.length).trim()
    if (!payloadJson) continue

    try {
      events.push(JSON.parse(payloadJson))
    } catch {
      // Malformed line: skip without throwing.
    }
  }

  return events
}