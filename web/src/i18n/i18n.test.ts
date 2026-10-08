import { describe, expect, test } from "vitest";
import { EN, FAQ_EN } from "./en";
import { RU, FAQ_RU } from "./ru";

/**
 * The dictionaries are plain records, so nothing at the type level stops RU
 * from missing a key (it would then silently fall back to English) or from
 * inventing one that no component uses. These tests keep the two languages
 * in lockstep.
 */
describe("i18n dictionaries", () => {
  test("RU covers exactly the keys of EN", () => {
    const en = Object.keys(EN).sort();
    const ru = Object.keys(RU).sort();

    expect(ru.filter((k) => !(k in EN))).toEqual([]);
    expect(en.filter((k) => !(k in RU))).toEqual([]);
    expect(ru).toEqual(en);
  });

  test("no translation is empty or left as its key", () => {
    for (const [lang, dict] of [
      ["en", EN],
      ["ru", RU],
    ] as const) {
      for (const [key, value] of Object.entries(dict)) {
        expect(value.trim(), `${lang}:${key}`).not.toBe("");
        expect(value, `${lang}:${key}`).not.toBe(key);
      }
    }
  });

  test("both languages label every instrument id", () => {
    const instrumentKeys = Object.keys(EN).filter((k) => k.startsWith("instr_"));
    expect(instrumentKeys.length).toBeGreaterThan(0);
    for (const key of instrumentKeys) {
      expect(RU[key], `RU is missing ${key}`).toBeTruthy();
    }
  });

  test("FAQ lists stay in sync", () => {
    expect(FAQ_RU.length).toBe(FAQ_EN.length);
    for (const [index, pair] of FAQ_EN.entries()) {
      expect(FAQ_RU[index].q.trim()).not.toBe("");
      expect(FAQ_RU[index].a.trim()).not.toBe("");
      expect(pair.q.trim()).not.toBe("");
      expect(pair.a.trim()).not.toBe("");
    }
  });
});
