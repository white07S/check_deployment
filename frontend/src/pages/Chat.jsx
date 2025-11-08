import ChatView from "../components/chat/ChatView";

export default function Chat({ user, llm_session_id }) {
  return <ChatView user={user} llmSessionId={llm_session_id} />;
}
