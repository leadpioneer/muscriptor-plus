/** The FastAPI `detail` of a failed response, or its raw body if it isn't one. */
export async function errorDetail(resp: Response): Promise<string> {
  const text = await resp.text();
  try {
    return JSON.parse(text).detail ?? text;
  } catch {
    // not JSON — keep the raw body
    return text;
  }
}
