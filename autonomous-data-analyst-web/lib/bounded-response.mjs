export class UpstreamResponseTooLarge extends Error {
  constructor() { super('Upstream response exceeded the configured size limit.'); }
}

export class InvalidUpstreamResponse extends Error {
  constructor() { super('Upstream response could not be read safely.'); }
}

export const MAX_JSON_RESPONSE_BYTES = 16 * 1024 * 1024;
export const MAX_CHART_RESPONSE_BYTES = 32 * 1024 * 1024;
const noStoreHeaders = { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' };

async function cancelBody(body) {
  try { await body?.cancel(); } catch { /* A failed or already-consumed stream needs no further action. */ }
}

/** Read a complete upstream body while keeping its retained bytes bounded. */
export async function readBoundedResponse(response, maxBytes) {
  const declared = response.headers.get('content-length');
  if (declared !== null && (!/^\d+$/.test(declared) || !Number.isSafeInteger(Number(declared)))) {
    await cancelBody(response.body);
    throw new InvalidUpstreamResponse();
  }
  const declaredBytes = declared === null ? null : Number(declared);
  if (declaredBytes !== null && declaredBytes > maxBytes) {
    await cancelBody(response.body);
    throw new UpstreamResponseTooLarge();
  }
  if (!response.body) {
    if (declaredBytes !== null && declaredBytes !== 0) throw new InvalidUpstreamResponse();
    return new Uint8Array();
  }

  const reader = response.body.getReader();
  const chunks = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxBytes) {
        await reader.cancel();
        throw new UpstreamResponseTooLarge();
      }
      chunks.push(value);
    }
  } catch (error) {
    if (error instanceof UpstreamResponseTooLarge) throw error;
    try { await reader.cancel(); } catch { /* Preserve the original stream failure. */ }
    throw new InvalidUpstreamResponse();
  }

  if (declaredBytes !== null && total !== declaredBytes) throw new InvalidUpstreamResponse();
  const result = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return result;
}

export async function buildBffResponse(upstream, limits = {}) {
  if (upstream.status >= 500) {
    await cancelBody(upstream.body);
    return Response.json({ detail: 'Analysis service unavailable.' }, { status: 502, headers: noStoreHeaders });
  }

  const contentType = (upstream.headers.get('content-type') ?? '').split(';', 1)[0].trim().toLowerCase();
  const isJson = contentType === 'application/json' || contentType.endsWith('+json');
  const isPng = contentType === 'image/png';
  if (upstream.status === 204 && !upstream.body) {
    return new Response(null, { status: 204, headers: noStoreHeaders });
  }
  if (!isJson && !isPng) {
    await cancelBody(upstream.body);
    return Response.json({ detail: 'Analysis service returned an invalid response.' }, { status: 502, headers: noStoreHeaders });
  }

  let bytes;
  try {
    bytes = await readBoundedResponse(upstream, isPng
      ? (limits.chartBytes ?? MAX_CHART_RESPONSE_BYTES)
      : (limits.jsonBytes ?? MAX_JSON_RESPONSE_BYTES));
  } catch (error) {
    const detail = error instanceof UpstreamResponseTooLarge
      ? 'Analysis service response exceeds the configured limit.'
      : error instanceof InvalidUpstreamResponse
        ? 'Analysis service returned an invalid response.'
        : 'Analysis service unavailable.';
    return Response.json({ detail }, { status: 502, headers: noStoreHeaders });
  }

  let body = bytes;
  const headers = new Headers(noStoreHeaders);
  if (isJson) {
    try {
      body = new TextEncoder().encode(new TextDecoder('utf-8', { fatal: true }).decode(bytes)
        .replaceAll('"/api/analysis/', '"/api/noha/analysis/'));
    } catch {
      return Response.json({ detail: 'Analysis service returned an invalid response.' }, { status: 502, headers: noStoreHeaders });
    }
    headers.set('Content-Type', 'application/json; charset=utf-8');
  } else {
    headers.set('Content-Type', 'image/png');
  }
  return new Response(body, { status: upstream.status, headers });
}
