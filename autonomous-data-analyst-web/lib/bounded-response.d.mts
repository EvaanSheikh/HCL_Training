export class UpstreamResponseTooLarge extends Error {}
export class InvalidUpstreamResponse extends Error {}
export function readBoundedResponse(response: Response, maxBytes: number): Promise<Uint8Array>;
export declare const MAX_JSON_RESPONSE_BYTES: number;
export declare const MAX_CHART_RESPONSE_BYTES: number;
export function buildBffResponse(response: Response, limits?: { jsonBytes?: number; chartBytes?: number }): Promise<Response>;
