import Chat from "./pages/Chat";

const USER_ID = "user-123";
const LLM_SESSION_ID = "llm-session-demo";

export default function App() {
  return <Chat user={USER_ID} llm_session_id={LLM_SESSION_ID} />;
}
