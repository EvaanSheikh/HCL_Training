import assert from 'node:assert/strict';
import {
  buildBffResponse,
  InvalidUpstreamResponse,
  readBoundedResponse,
  UpstreamResponseTooLarge,
} from '../lib/bounded-response.mjs';

const text = (bytes) => new TextDecoder().decode(bytes);

assert.equal(text(await readBoundedResponse(new Response('abc'), 4)), 'abc');
assert.equal(text(await readBoundedResponse(new Response('abcd'), 4)), 'abcd');

let declaredCancel = false;
const declaredTooLarge = new Response(new ReadableStream({
  cancel() { declaredCancel = true; },
}), { headers: { 'content-length': '5' } });
await assert.rejects(readBoundedResponse(declaredTooLarge, 4), UpstreamResponseTooLarge);
assert.equal(declaredCancel, true, 'declared oversize should cancel before reading');

let streamedCancel = false;
const noLengthTooLarge = new Response(new ReadableStream({
  start(controller) { controller.enqueue(new Uint8Array(3)); controller.enqueue(new Uint8Array(2)); },
  cancel() { streamedCancel = true; },
}));
await assert.rejects(readBoundedResponse(noLengthTooLarge, 4), UpstreamResponseTooLarge);
assert.equal(streamedCancel, true, 'streamed oversize should cancel upstream consumption');

const incorrectLength = new Response('abc', { headers: { 'content-length': '2' } });
await assert.rejects(readBoundedResponse(incorrectLength, 4), InvalidUpstreamResponse);

for (const contentLength of ['-1', 'invalid', '9007199254740992']) {
  const malformedLength = { headers: new Headers({ 'content-length': contentLength }), body: null };
  await assert.rejects(readBoundedResponse(malformedLength, 4), InvalidUpstreamResponse);
}

const failedStream = new Response(new ReadableStream({
  start(controller) { controller.error(new Error('secret upstream implementation detail')); },
}));
await assert.rejects(readBoundedResponse(failedStream, 4), InvalidUpstreamResponse);

const json = await buildBffResponse(new Response(
  JSON.stringify({ chart: '/api/analysis/session/charts/asset' }),
  { status: 201, headers: { 'content-type': 'application/json; charset=utf-8', 'connection': 'keep-alive', 'x-internal': 'do-not-forward' } },
), { jsonBytes: 128 });
assert.equal(json.status, 201);
assert.equal(json.headers.get('content-type'), 'application/json; charset=utf-8');
assert.equal(json.headers.get('connection'), null);
assert.equal(json.headers.get('x-internal'), null);
assert.deepEqual(await json.json(), { chart: '/api/noha/analysis/session/charts/asset' });

const pngBytes = new Uint8Array([137, 80, 78, 71, 0, 1]);
const png = await buildBffResponse(new Response(pngBytes, {
  headers: { 'content-type': 'image/png', 'content-length': String(pngBytes.length), 'x-internal': 'secret' },
}), { chartBytes: pngBytes.length });
assert.equal(png.status, 200);
assert.equal(png.headers.get('content-type'), 'image/png');
assert.equal(png.headers.get('x-internal'), null);
assert.deepEqual(new Uint8Array(await png.arrayBuffer()), pngBytes);

const internalError = await buildBffResponse(new Response('secret stack trace', {
  status: 500, headers: { 'content-type': 'text/plain' },
}));
assert.equal(internalError.status, 502);
assert.deepEqual(await internalError.json(), { detail: 'Analysis service unavailable.' });

const tooLargeJson = await buildBffResponse(new Response('12345', {
  headers: { 'content-type': 'application/json', 'content-length': '5' },
}), { jsonBytes: 4 });
assert.equal(tooLargeJson.status, 502);
assert.match((await tooLargeJson.json()).detail, /exceeds the configured limit/);

console.log('Bounded BFF response tests passed: byte boundaries, malformed/dishonest/missing lengths, stream failure/cancel, JSON/PNG compatibility, and safe errors.');
