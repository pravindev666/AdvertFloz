/**
 * AES-256-GCM token encryption using WebCrypto. The key is a Worker secret held separately
 * from the stored ciphertext; D1 never contains plaintext tokens.
 */
function b64ToBytes(value: string): Uint8Array {
  const binary = atob(value.replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function bytesToB64(bytes: Uint8Array): string {
  let binary = "";
  bytes.forEach((b) => {
    binary += String.fromCharCode(b);
  });
  return btoa(binary);
}

async function importKey(keyB64: string): Promise<CryptoKey> {
  const raw = b64ToBytes(keyB64);
  if (raw.length !== 32) throw new Error("TOKEN_ENCRYPTION_KEY must decode to 32 bytes");
  return crypto.subtle.importKey("raw", raw, { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
}

export interface SealedToken {
  keyId: string;
  nonce: string;
  ciphertext: string;
}

export async function sealToken(plaintext: string, keyB64: string, keyId = "k1"): Promise<SealedToken> {
  const key = await importKey(keyB64);
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, new TextEncoder().encode(plaintext));
  return { keyId, nonce: bytesToB64(nonce), ciphertext: bytesToB64(new Uint8Array(ciphertext)) };
}

export async function openToken(sealed: SealedToken, keyB64: string): Promise<string> {
  const key = await importKey(keyB64);
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: b64ToBytes(sealed.nonce) },
    key,
    b64ToBytes(sealed.ciphertext),
  );
  return new TextDecoder().decode(plaintext);
}
