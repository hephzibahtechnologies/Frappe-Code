// Run from apps/helpdesk/desk (needs node_modules for dayjs):
//   node --test tests/dateDisplayFormat.test.ts
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, test } from "node:test";
import dayjs from "dayjs";
import {
  SBIQC_DATE_FORMAT,
  displayFormat,
  usesSbiqcDateFormat,
} from "../src/dateDisplayFormat.ts";

const OTHER_FORMATS = [
  "yyyy-mm-dd",
  "dd-mm-yyyy",
  "dd/mm/yyyy",
  "dd.mm.yyyy",
  "mm/dd/yyyy",
  "mm-dd-yyyy",
];

describe("displayFormat selection", () => {
  afterEach(() => {
    delete (globalThis as any).date_format;
  });

  test("opt-in format returns the dd-MMM-yyyy pattern", () => {
    assert.equal(SBIQC_DATE_FORMAT, "dd-MMM-yyyy");
    assert.equal(displayFormat("LEGACY", "NEW", "dd-MMM-yyyy"), "NEW");
    assert.ok(usesSbiqcDateFormat("dd-MMM-yyyy"));
  });

  test("every other shipped format keeps the legacy pattern (backward compatible)", () => {
    for (const f of OTHER_FORMATS) {
      assert.equal(displayFormat("LEGACY", "NEW", f), "LEGACY", f);
      assert.ok(!usesSbiqcDateFormat(f), f);
    }
  });

  test("missing or empty site format keeps the legacy pattern", () => {
    assert.equal(displayFormat("LEGACY", "NEW", ""), "LEGACY");
    assert.equal(displayFormat("LEGACY", "NEW", undefined as any), "LEGACY");
  });

  test("the spelling is exact: lowercase mmm is not the opt-in value", () => {
    assert.equal(displayFormat("LEGACY", "NEW", "dd-mmm-yyyy"), "LEGACY");
  });

  test("reads the boot value window.date_format at call time", () => {
    assert.equal(displayFormat("LEGACY", "NEW"), "LEGACY");
    (globalThis as any).date_format = "dd-MMM-yyyy";
    assert.equal(displayFormat("LEGACY", "NEW"), "NEW");
    (globalThis as any).date_format = "dd-mm-yyyy";
    assert.equal(displayFormat("LEGACY", "NEW"), "LEGACY");
  });
});

describe("dd-MMM-yyyy patterns used by Helpdesk render as 05-Nov-2026", () => {
  const d = dayjs(new Date(2026, 10, 5, 14, 30, 0)); // Thu 05 Nov 2026 14:30
  const cases: Array<[string, string]> = [
    ["ddd, DD-MMM-YYYY h:mm A", "Thu, 05-Nov-2026 2:30 PM"], // dateTooltipFormat
    ["ddd, DD-MMM-YYYY h:mm a", "Thu, 05-Nov-2026 2:30 pm"], // call log detail
    ["DD-MMM-YYYY, dddd", "05-Nov-2026, Thursday"], // call day label
    ["DD-MMM-YYYY, h:mm A", "05-Nov-2026, 2:30 PM"], // article modified
    ["dddd, DD-MMM-YYYY h:mm A", "Thursday, 05-Nov-2026 2:30 PM"], // LLLL replacement
    ["DD-MMM-YYYY hh:mm A", "05-Nov-2026 02:30 PM"], // search results
    ["DD-MMM-YYYY", "05-Nov-2026"], // holidays
  ];
  for (const [pattern, expected] of cases) {
    test(pattern, () => assert.equal(d.format(pattern), expected));
  }

  test("the site format itself (DD-MMM-YYYY, as getDateFormat() uppercases it) renders too", () => {
    assert.equal(d.format("dd-MMM-yyyy".toUpperCase()), "05-Nov-2026");
  });
});

describe("drift guard over desk/src", () => {
  function walk(dir: string): string[] {
    return readdirSync(dir).flatMap((n) => {
      const p = join(dir, n);
      return statSync(p).isDirectory()
        ? walk(p)
        : /\.(vue|ts|js)$/.test(n)
        ? [p]
        : [];
    });
  }
  const files = walk(join(import.meta.dirname, "..", "src")).filter(
    (f) => !f.endsWith("dateDisplayFormat.ts")
  );
  const calls: Array<{ file: string; legacy: string; sbiqc: string }> = [];
  for (const file of files) {
    const text = readFileSync(file, "utf8");
    for (const m of text.matchAll(
      /displayFormat\(\s*["']([^"']+)["']\s*,\s*["']([^"']+)["']/g
    )) {
      calls.push({ file, legacy: m[1], sbiqc: m[2] });
    }
  }

  test("all fixed-pattern surfaces are wired (8 call sites)", () => {
    assert.equal(calls.length, 8, JSON.stringify(calls.map((c) => c.file)));
  });

  test("every call pairs a legacy pattern with a DD-MMM-YYYY pattern", () => {
    for (const c of calls) {
      assert.ok(c.sbiqc.includes("DD-MMM-YYYY"), `${c.file}: ${c.sbiqc}`);
      assert.ok(!c.legacy.includes("DD-MMM-YYYY"), `${c.file}: ${c.legacy}`);
    }
  });

  test("machine formats stay fixed: no displayFormat on YYYY-MM-DD", () => {
    for (const c of calls) {
      assert.ok(!/^YYYY-MM-DD/.test(c.legacy), `${c.file}: ${c.legacy}`);
    }
  });
});
