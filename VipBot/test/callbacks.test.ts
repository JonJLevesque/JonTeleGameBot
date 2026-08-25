import { describe, expect, it } from "vitest";
import { signCb, verifyCb } from "../src/domain/callbacks";

describe("signed callbacks", () => {
  it("round trips and rejects tampering", async () => {
    const d = await signCb("k", "drop", "42");
    expect(d.length).toBeLessThanOrEqual(64);
    expect(await verifyCb("k", d)).toEqual({ kind: "drop", payload: "42" });
    expect(await verifyCb("k", d.replace("42", "43"))).toBeNull();
    expect(await verifyCb("other", d)).toBeNull();
  });
});
