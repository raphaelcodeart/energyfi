/**
 * The visitor's IP as nginx saw it, to pass on to the API. Without it the
 * API's rate limits would see only this server and throttle every visitor
 * together. nginx always overwrites X-Real-IP, so clients cannot forge it.
 */
export function clientIpHeaders(request: Request): Record<string, string> {
  const ip = request.headers.get("x-real-ip");
  return ip ? { "X-Real-IP": ip } : {};
}
