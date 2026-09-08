import { describe, it, expect } from 'vitest'
import { parseRagSse, parseSseEvents } from '../ragApi'

/**
 * Unit tests for the pure SSE parser (Phase 8 §8.2).
 * The wire contract being parsed (Phase 6):
 *     : connected\n\n
 *     data: {"type":"token","text":"..."}\n\n
 *     data: {"type":"final","sources":[...],"diagnostics":{...}}\n\n
 */

describe('parseSseEvents', () => {
  it('extracts only objects from data: lines', () => {
    const body = [
      ': connected\n',
      '',
      'data: {"type":"token","text":"Hi"}',
      '',
      'data: {"type":"final","sources":[],"diagnostics":{}}',
      '\n',
    ].join('\n')

    const events = parseSseEvents(body)

    expect(events).toEqual([
      { type: 'token', text: 'Hi' },
      { type: 'final', sources: [], diagnostics: {} },
    ])
  })

  it('ignores non-data lines (comments) and blank lines', () => {
    const body = ': connected\n\ndata: {"type":"token","text":"A"}\n'
    const events = parseSseEvents(body)
    expect(events).toHaveLength(1)
    expect(events[0]).toEqual({ type: 'token', text: 'A' })
  })

  it('skips malformed JSON lines without throwing', () => {
    const body = 'data: {broken json\n\ndata: {"type":"token","text":"ok"}\n'
    const events = parseSseEvents(body)
    expect(events).toHaveLength(1)
    expect(events[0]).toEqual({ type: 'token', text: 'ok' })
  })

  it('tolerates CRLF line endings', () => {
    const body = ': connected\r\n\r\ndata: {"type":"token","text":"CRLF"}\r\n'
    const events = parseSseEvents(body)
    expect(events).toEqual([{ type: 'token', text: 'CRLF' }])
  })
})

describe('parseRagSse', () => {
  it('accumulates the full answer from token-only events', () => {
    const body = [
      ': connected\n\n',
      'data: {"type":"token","text":"The answer"}\n\n',
      'data: {"type":"token","text":" is grounded."}\n\n',
    ].join('')

    const result = parseRagSse(body)

    expect(result.answer).toBe('The answer is grounded.')
    expect(result.sources).toEqual([])
    expect(result.diagnostics).toEqual({})
  })

  it('enriches with sources and diagnostics from the final event', () => {
    const sources = [
      { chunk_id: 'c1', filename: 'report.pdf', page_start: 2, page_end: 4 },
    ]
    const diagnostics = { cache_hit: false, chunks_retrieved: 6, sources_used: 1 }
    const body = [
      `data: {"type":"token","text":"Summary:"}\n\n`,
      `data: ${JSON.stringify({ type: 'final', sources, diagnostics })}\n\n`,
    ].join('')

    const result = parseRagSse(body)

    expect(result.answer).toBe('Summary:')
    expect(result.sources).toEqual(sources)
    expect(result.diagnostics).toEqual(diagnostics)
  })

  it('yields [] for a final event with empty sources', () => {
    const body =
      'data: {"type":"final","sources":[],"diagnostics":{"insufficient_evidence":true}}\n\n'

    const result = parseRagSse(body)

    expect(result.sources).toEqual([])
    expect(result.diagnostics.insufficient_evidence).toBe(true)
  })

  it('ignores comment lines interspersed among data lines', () => {
    const body = [
      ': connected\n\n',
      'data: {"type":"token","text":"Hi"}\n\n',
      ': keepalive ping\n\n',
      'data: {"type":"token","text":"!"}\n\n',
    ].join('')

    const result = parseRagSse(body)

    expect(result.answer).toBe('Hi!')
  })

  it('skips malformed lines without throwing or losing subsequent tokens', () => {
    const body = [
      'data: {"type":"token","text":"part1"}\n\n',
      'data: not-json\n\n',
      'data: {"type":"token","text":"part2"}\n\n',
    ].join('')

    const result = parseRagSse(body)

    expect(result.answer).toBe('part1part2')
  })

  it('captures a mid-stream error event surfaced by the backend', () => {
    const body = 'data: {"type":"error","detail":"Internal error during answer generation."}\n\n'

    const result = parseRagSse(body)

    expect(result.error).toBe('Internal error during answer generation.')
  })

  it('returns an empty answer object for an empty body', () => {
    const result = parseRagSse('')
    expect(result).toEqual({ answer: '', sources: [], diagnostics: {} })
  })
})