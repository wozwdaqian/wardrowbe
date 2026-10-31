export const API_BASE_PATH = '/api/v1';

interface FetchOptions extends RequestInit {
  params?: Record<string, string>;
}

class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(message: string, status: number, data: unknown) {
    super(message);
    this.status = status;
    this.data = data;
    this.name = 'ApiError';
  }
}

class NetworkError extends Error {
  constructor(message: string = 'Network error. Please check your connection.') {
    super(message);
    this.name = 'NetworkError';
  }
}

let accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

async function fetchApi<T>(endpoint: string, options: FetchOptions = {}): Promise<T> {
  const { params, ...fetchOptions } = options;

  let url = `${API_BASE_PATH}${endpoint}`;
  if (params) {
    const searchParams = new URLSearchParams(params);
    url += `?${searchParams.toString()}`;
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(fetchOptions.headers as Record<string, string>),
  };

  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...fetchOptions,
      headers,
      credentials: 'include',
    });
  } catch (err) {
    if (!navigator.onLine) {
      throw new NetworkError('You appear to be offline. Please check your connection.');
    }
    throw new NetworkError('Unable to connect to server. Please try again.');
  }

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const message = (typeof data.detail === 'string' ? data.detail : data.detail?.message)
      || data.error?.message
      || 'An error occurred';
    throw new ApiError(message, response.status, data);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// POSTs multipart form data; the browser sets the boundary, so no Content-Type here.
export async function uploadApi<T>(endpoint: string, body: FormData): Promise<T> {
  const headers: Record<string, string> = {};
  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`;
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE_PATH}${endpoint}`, {
      method: 'POST',
      headers,
      body,
      credentials: 'include',
    });
  } catch {
    throw new NetworkError('Unable to connect to server. Please try again.');
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const message = (typeof data.detail === 'string' ? data.detail : data.detail?.message)
      || 'An error occurred';
    throw new ApiError(message, response.status, data);
  }
  return response.json();
}

export type StreamEvent = { type: string; [key: string]: unknown };

// POSTs JSON and yields each server-sent event's `data:` payload as it arrives.
export async function* streamApi(
  endpoint: string,
  body?: unknown,
  signal?: AbortSignal
): AsyncGenerator<StreamEvent> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  };
  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`;
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE_PATH}${endpoint}`, {
      method: 'POST',
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'include',
      signal,
    });
  } catch (err) {
    if (signal?.aborted) throw err;
    throw new NetworkError('Unable to connect to server. Please try again.');
  }
  if (!response.ok || !response.body) {
    const data = await response.json().catch(() => ({}));
    const message = (typeof data.detail === 'string' ? data.detail : data.detail?.message)
      || 'An error occurred';
    throw new ApiError(message, response.status, data);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (value) buffer += decoder.decode(value, { stream: !done });
    let boundary = buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const data = block
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
        .join('\n');
      if (data) yield JSON.parse(data) as StreamEvent;
      boundary = buffer.indexOf('\n\n');
    }
    if (done) return;
  }
}

export const api = {
  get: <T>(endpoint: string, options?: FetchOptions) =>
    fetchApi<T>(endpoint, { ...options, method: 'GET' }),

  post: <T>(endpoint: string, data?: unknown, options?: FetchOptions) =>
    fetchApi<T>(endpoint, {
      ...options,
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    }),

  patch: <T>(endpoint: string, data?: unknown, options?: FetchOptions) =>
    fetchApi<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body: data ? JSON.stringify(data) : undefined,
    }),

  delete: <T>(endpoint: string, options?: FetchOptions) =>
    fetchApi<T>(endpoint, { ...options, method: 'DELETE' }),
};

const handledErrors = new WeakSet<object>();

export function getErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === 'object') handledErrors.add(error);
  if (error instanceof ApiError && error.status < 500) return error.message;
  return fallback;
}

export function isErrorHandled(error: unknown): boolean {
  return error !== null && typeof error === 'object' && handledErrors.has(error);
}

export { ApiError, NetworkError };
