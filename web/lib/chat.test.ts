import { expect, test } from "bun:test";
import { chatWindow, type ChatMessage } from "./chat";

const m = (role: ChatMessage["role"], content: string): ChatMessage => ({ role, content });

test("chatWindow keeps the latest messages, starting with the user", () => {
  const msgs = [m("user", "1"), m("assistant", "2"), m("user", "3"), m("assistant", "4"), m("user", "5")];
  expect(chatWindow(msgs, 3).map((x) => x.content)).toEqual(["3", "4", "5"]);
  expect(chatWindow(msgs, 2).map((x) => x.content)).toEqual(["5"]);
  expect(chatWindow(msgs).length).toBe(5);
});
