/** Download `blob` as `filename` via a transient object URL.
 *
 * Revoking right after `click()` can cancel the download in Firefox/Safari,
 * which may start reading the URL asynchronously; hold it for a minute.
 */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
