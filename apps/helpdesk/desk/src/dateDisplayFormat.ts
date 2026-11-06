/**
 * Display patterns for Helpdesk surfaces that historically used their own fixed English
 * pattern instead of the site's System Settings date format (tooltips, day separators, ...).
 *
 * The optional site format `dd-MMM-yyyy` (05-Nov-2026) is provided by the `sbiqc_core` app.
 * When a site selects it, these surfaces follow it so Helpdesk reads the same as the rest of
 * the ERP. For every other format the shipped pattern is returned unchanged, so sites that
 * have not opted in see no difference at all.
 *
 * Only for display strings. Never use it for API filters or other machine formats
 * (`YYYY-MM-DD`): those must stay fixed.
 *
 * No imports on purpose, so it can be unit-tested with plain `node --test`.
 */

/** Site format value (System Settings > Date Format) that this module reacts to. */
export const SBIQC_DATE_FORMAT = "dd-MMM-yyyy";

/** Same value as Frappe's boot data, read at call time (boot data is set before the bundle runs). */
function siteDateFormat(): string {
  return ((globalThis as any).date_format || "") as string;
}

/** True when the site selected the optional `dd-MMM-yyyy` format. */
export function usesSbiqcDateFormat(siteFormat: string = siteDateFormat()): boolean {
  return siteFormat === SBIQC_DATE_FORMAT;
}

/**
 * Pick the dayjs pattern for a fixed-pattern display surface.
 * @param legacy  the pattern the surface always used
 * @param sbiqc   the equivalent pattern written with `DD-MMM-YYYY`
 */
export function displayFormat(
  legacy: string,
  sbiqc: string,
  siteFormat: string = siteDateFormat()
): string {
  return usesSbiqcDateFormat(siteFormat) ? sbiqc : legacy;
}
