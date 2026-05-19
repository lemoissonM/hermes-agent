export type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
};

export default function MessageList({ messages }: { messages: Message[] }) {
  return (
    <div className="message-list">
      {messages.map((m) => (
        <div key={m.id} className={`message message-${m.role}`}>
          <div className="message-role">{m.role}</div>
          <div className="message-body">{m.content}</div>
        </div>
      ))}
    </div>
  );
}
