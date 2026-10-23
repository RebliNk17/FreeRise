export type ChatMessage = { role: "user" | "assistant"; content: string };

/** The API takes at most 20 messages: keep the latest, starting on a user turn. */
export function chatWindow(messages: ChatMessage[], max = 20): ChatMessage[] {
  const out = messages.slice(-max);
  while (out.length && out[0].role !== "user") out.shift();
  return out;
}
