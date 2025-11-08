import { useEffect, useState } from "react";
import { Edit2, Send, X } from "lucide-react";

function constructPrompt(prompt, userData) {
  if (!prompt) {
    return "";
  }
  let prepared = `Persona: ${prompt.persona}\n\nTask: ${prompt.task}\n\n`;
  if (prompt.if_task_need_data) {
    if (userData?.trim()) {
      prepared += `Data:\n${userData.trim()}\n\n`;
    } else if (prompt.data) {
      prepared += `Data Format Example:\n${prompt.data}\n\n`;
    }
  }
  prepared += `Expected Response Format: ${prompt.response}`;
  return prepared.trim();
}

export default function PromptPreview({ prompt, onSend, onCancel }) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedPrompt, setEditedPrompt] = useState("");
  const [userData, setUserData] = useState("");

  useEffect(() => {
    setEditedPrompt(constructPrompt(prompt, ""));
    setUserData("");
    setIsEditing(false);
  }, [prompt]);

  const handleDataChange = (event) => {
    const value = event.target.value;
    setUserData(value);
    setEditedPrompt(constructPrompt(prompt, value));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="flex w-full max-w-3xl flex-col border-2 border-black bg-white">
        <div className="border-b-2 border-black bg-gray-50 px-5 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-bold text-gray-900">Use Prompt</h2>
              <p className="text-sm text-gray-600">{prompt.persona}</p>
            </div>
            <button
              type="button"
              onClick={onCancel}
              className="border-2 border-black p-2 transition-colors hover:bg-red-50"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {prompt.if_task_need_data && (
            <div>
              <label className="block text-sm font-semibold text-gray-900">
                Provide your data (optional)
              </label>
              <textarea
                value={userData}
                onChange={handleDataChange}
                rows={4}
                placeholder={prompt.data || "Paste the required data here."}
                className="mt-2 w-full border-2 border-black px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-primary-light"
              />
            </div>
          )}

          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-semibold text-gray-900">
                {isEditing ? "Edit Prompt" : "Preview Prompt"}
              </span>
              <button
                type="button"
                onClick={() => setIsEditing((prev) => !prev)}
                className="flex items-center gap-1 border-2 border-gray-300 px-3 py-1 text-xs font-semibold text-gray-700 transition-colors hover:border-black"
              >
                <Edit2 className="h-3 w-3" />
                {isEditing ? "Preview" : "Edit"}
              </button>
            </div>
            {isEditing ? (
              <textarea
                value={editedPrompt}
                onChange={(event) => setEditedPrompt(event.target.value)}
                rows={16}
                className="w-full border-2 border-black bg-white px-3 py-2 font-mono text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-primary-light"
              />
            ) : (
              <div className="border-2 border-gray-300 bg-gray-50 p-4 font-mono text-sm text-gray-800 whitespace-pre-wrap">
                {editedPrompt}
              </div>
            )}
          </div>

          <div>
            <p className="text-sm font-semibold text-gray-900">Keywords</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {(prompt.keywords_used_for_search || []).map((keyword) => (
                <span key={keyword} className="border border-gray-300 bg-gray-50 px-2 py-1 text-xs">
                  {keyword}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="border-t-2 border-black bg-gray-50 px-5 py-4">
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => onSend(editedPrompt)}
              className="flex flex-1 items-center justify-center gap-2 border-2 border-black bg-primary px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-primary-dark"
            >
              <Send className="h-4 w-4" />
              Send to Chat
            </button>
            <button
              type="button"
              onClick={onCancel}
              className="border-2 border-black px-6 py-3 text-sm font-semibold text-gray-900 transition-colors hover:bg-gray-100"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
