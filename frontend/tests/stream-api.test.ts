import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, setAccessToken, streamApi } from '@/lib/api';

function sse(chunks: string[], status = 200) {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { status, headers: { 'content-type': 'text/event-stream' } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  setAccessToken(null);
});

describe('streamApi', () => {
  it('yields events split across network chunks and sends the token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      sse(['data: {"type":"tool","na', 'me":"get_weather"}\n\ndata: {"type":"done"}', '\n\n'])
    );
    vi.stubGlobal('fetch', fetchMock);
    setAccessToken('tok');
    const events = [];
    for await (const event of streamApi('/assistant/x', { content: 'hi' })) events.push(event);
    expect(events).toEqual([{ type: 'tool', name: 'get_weather' }, { type: 'done' }]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/assistant/x');
    expect(init.headers.Authorization).toBe('Bearer tok');
    expect(init.body).toBe('{"content":"hi"}');
  });

  it('raises ApiError with the server detail on failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'Too many requests' }), { status: 429 })
      )
    );
    const iterator = streamApi('/assistant/x');
    await expect(iterator.next()).rejects.toBeInstanceOf(ApiError);
  });
});
