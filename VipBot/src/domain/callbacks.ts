/** Signed callback data: `kind:payload:sig8`. Telegram caps callback_data at 64 bytes. */
async function hmac8(key: string, msg: string): Promise<string> {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(msg));
  return [...new Uint8Array(sig)].slice(0, 4).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function signCb(key: string, kind: string, payload: string): Promise<string> {
  const body = `${kind}:${payload}`;
  return `${body}:${await hmac8(key, body)}`;
}

export async function verifyCb(key: string, data: string): Promise<{ kind: string; payload: string } | null> {
  const i = data.lastIndexOf(":");
  if (i < 0) return null;
  const body = data.slice(0, i);
  const sig = data.slice(i + 1);
  if ((await hmac8(key, body)) !== sig) return null;
  const j = body.indexOf(":");
  return j < 0 ? { kind: body, payload: "" } : { kind: body.slice(0, j), payload: body.slice(j + 1) };
}
