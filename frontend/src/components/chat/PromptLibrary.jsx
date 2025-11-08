import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, Filter, Plus, Search, X } from "lucide-react";

import { chatApi } from "./api";
import PromptCard from "./PromptCard";
import PromptForm from "./PromptForm";

export default function PromptLibrary({ user, onSelectPrompt, onClose }) {
  const [prompts, setPrompts] = useState([]);
  const [filteredPrompts, setFilteredPrompts] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingPrompt, setEditingPrompt] = useState(null);
  const [searchKeywords, setSearchKeywords] = useState("");
  const [filterUserCreated, setFilterUserCreated] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadPrompts = useCallback(async () => {
    setIsLoading(true);
    try {
      const keywordFilter = searchKeywords
        ? searchKeywords
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean)
            .join(",")
        : undefined;

      const data = await chatApi.listPrompts(
        { user_created: filterUserCreated, keywords: keywordFilter },
        user
      );
      setPrompts(data);
      setError("");
    } catch (err) {
      console.error("Failed to load prompts", err);
      setError(err.message || "Failed to load prompts");
    } finally {
      setIsLoading(false);
    }
  }, [user, filterUserCreated, searchKeywords]);

  useEffect(() => {
    loadPrompts();
  }, [loadPrompts]);

  useEffect(() => {
    if (!prompts.length) {
      setFilteredPrompts([]);
      return;
    }
    setFilteredPrompts(prompts);
  }, [prompts]);

  const dismissMessages = useCallback(() => {
    setSuccess("");
    setError("");
  }, []);

  const handleCreatePrompt = async (formData) => {
    try {
      await chatApi.createPrompt(formData, user);
      setSuccess("Prompt created successfully.");
      setShowForm(false);
      setEditingPrompt(null);
      loadPrompts();
      setTimeout(dismissMessages, 3000);
    } catch (err) {
      setError(err.message || "Failed to create prompt.");
    }
  };

  const handleUpdatePrompt = async (promptId, formData) => {
    try {
      await chatApi.updatePrompt(promptId, formData, user);
      setSuccess("Prompt updated successfully.");
      setShowForm(false);
      setEditingPrompt(null);
      loadPrompts();
      setTimeout(dismissMessages, 3000);
    } catch (err) {
      setError(err.message || "Failed to update prompt.");
    }
  };

  const handleDeletePrompt = async (promptId) => {
    if (!window.confirm("Delete this prompt permanently?")) {
      return;
    }
    try {
      await chatApi.deletePrompt(promptId, user);
      setSuccess("Prompt deleted successfully.");
      loadPrompts();
      setTimeout(dismissMessages, 3000);
    } catch (err) {
      setError(err.message || "Failed to delete prompt.");
    }
  };

  const handleCopyPrompt = async (promptId) => {
    try {
      await chatApi.copyPrompt(promptId, user);
      setSuccess("Prompt copied to your library.");
      loadPrompts();
      setTimeout(dismissMessages, 3000);
    } catch (err) {
      setError(err.message || "Failed to copy prompt.");
    }
  };

  const displayedPrompts = useMemo(() => {
    if (!searchKeywords.trim()) {
      return filteredPrompts;
    }
    const keywords = searchKeywords
      .toLowerCase()
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    if (!keywords.length) {
      return filteredPrompts;
    }
    return filteredPrompts.filter((prompt) => {
      const promptKeywords = (prompt.keywords_used_for_search || []).map((kw) => kw.toLowerCase());
      const persona = (prompt.persona || "").toLowerCase();
      const task = (prompt.task || "").toLowerCase();
      return keywords.some(
        (keyword) =>
          promptKeywords.some((item) => item.includes(keyword)) ||
          persona.includes(keyword) ||
          task.includes(keyword)
      );
    });
  }, [filteredPrompts, searchKeywords]);

  return (
    <div className="flex h-full flex-col bg-white">
      <div className="border-b-2 border-black bg-white p-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Prompt Library</h1>
            <p className="text-sm text-gray-600">
              Browse reusable personas and tasks to accelerate your workflow.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                setEditingPrompt(null);
                setShowForm(true);
              }}
              className="flex items-center gap-2 border-2 border-black bg-primary px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-dark"
            >
              <Plus className="h-4 w-4" />
              New Prompt
            </button>
            {onClose && (
              <button
                type="button"
                onClick={onClose}
                className="border-2 border-black px-3 py-2 text-sm font-semibold text-gray-900 transition-colors hover:bg-gray-100"
              >
                Close
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="border-b border-gray-200 bg-white p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
            <input
              type="text"
              value={searchKeywords}
              onChange={(event) => setSearchKeywords(event.target.value)}
              placeholder="Search by keywords, persona, or task"
              className="w-full border-2 border-black pl-9 pr-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-light"
            />
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-700">
            <Filter className="h-4 w-4" />
            <button
              type="button"
              onClick={() => setFilterUserCreated((prev) => (prev === true ? null : true))}
              className={`border-2 px-3 py-1 transition ${
                filterUserCreated === true
                  ? "border-black bg-primary text-white"
                  : "border-gray-300 text-gray-800 hover:border-black"
              }`}
            >
              My Prompts
            </button>
            <button
              type="button"
              onClick={() => setFilterUserCreated((prev) => (prev === false ? null : false))}
              className={`border-2 px-3 py-1 transition ${
                filterUserCreated === false
                  ? "border-black bg-primary text-white"
                  : "border-gray-300 text-gray-800 hover:border-black"
              }`}
            >
              Community
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="mx-4 mt-4 flex items-center justify-between border-2 border-primary bg-red-50 px-4 py-3 text-sm text-primary">
          <span>{error}</span>
          <button type="button" onClick={() => setError("")} className="p-1">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
      {success && (
        <div className="mx-4 mt-4 flex items-center justify-between border-2 border-green-600 bg-green-100 px-4 py-3 text-sm text-green-700">
          <span>{success}</span>
          <button type="button" onClick={() => setSuccess("")} className="p-1">
            <Check className="h-4 w-4" />
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-4">
        {isLoading ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-sm text-gray-600">
            <div className="h-10 w-10 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            Loading prompts...
          </div>
        ) : displayedPrompts.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-sm text-gray-600">
            <p>No prompts match the current filters.</p>
            <button
              type="button"
              onClick={() => {
                setEditingPrompt(null);
                setShowForm(true);
              }}
              className="border-2 border-black px-4 py-2 font-semibold text-gray-900 transition-colors hover:bg-primary hover:text-white"
            >
              Create your first prompt
            </button>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {displayedPrompts.map((prompt) => (
              <PromptCard
                key={prompt.id}
                prompt={prompt}
                isOwner={Boolean(prompt.is_owner)}
                onSelect={() => onSelectPrompt?.(prompt)}
                onEdit={() => {
                  setEditingPrompt(prompt);
                  setShowForm(true);
                }}
                onCopy={() => handleCopyPrompt(prompt.id)}
                onDelete={() => handleDeletePrompt(prompt.id)}
              />
            ))}
          </div>
        )}
      </div>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="w-full max-w-2xl overflow-hidden border-2 border-black bg-white">
            <PromptForm
              prompt={editingPrompt}
              onSubmit={(data) =>
                editingPrompt
                  ? handleUpdatePrompt(editingPrompt.id, data)
                  : handleCreatePrompt(data)
              }
              onCancel={() => {
                setShowForm(false);
                setEditingPrompt(null);
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
