import { describe, expect, it } from "vitest";
import { readResetToken } from "./resetToken";

describe("readResetToken", () => {
  it("le o token do fragmento", () => {
    expect(readResetToken("#token=abc_DEF-123", "")).toBe("abc_DEF-123");
  });

  it("aceita o formato antigo na query", () => {
    expect(readResetToken("", "?token=abc_DEF-123")).toBe("abc_DEF-123");
  });

  it("prefere o fragmento quando os dois existem", () => {
    expect(readResetToken("#token=novo", "?token=antigo")).toBe("novo");
  });

  it("ignora espacos em volta", () => {
    expect(readResetToken("#token=%20abc%20", "")).toBe("abc");
  });

  it.each([["", ""], ["#", "?"], ["#outro=1", "?x=2"], ["#token=", ""]])(
    "devolve vazio quando nao ha token (%j, %j)",
    (hash, search) => {
      expect(readResetToken(hash, search)).toBe("");
    }
  );

  it("nao confunde com outros parametros", () => {
    expect(readResetToken("#a=1&token=xyz&b=2", "")).toBe("xyz");
  });
});
