import { useEffect, useState } from "react";
import { Plus, Trash2, X } from "lucide-react";

const emptyForm = {
  persona: "",
  task: "",
  if_task_need_data: false,
  data: "",
  response: "",
  keywords_used_for_search: [],
};

export default function PromptForm({ prompt, onSubmit, onCancel }) {
  const [formData, setFormData] = useState(emptyForm);
  const [newKeyword, setNewKeyword] = useState("");
  const [errors, setErrors] = useState({});

  useEffect(() => {
    if (prompt) {
      setFormData({
        persona: prompt.persona || "",
        task: prompt.task || "",
        if_task_need_data: Boolean(prompt.if_task_need_data),
        data: prompt.data || "",
        response: prompt.response || "",
        keywords_used_for_search: [...(prompt.keywords_used_for_search || [])],
      });
    } else {
      setFormData(emptyForm);
    }
  }, [prompt]);

  const validate = () => {
    const nextErrors = {};
    if (!formData.persona.trim()) {
      nextErrors.persona = "Persona is required.";
    }
    if (!formData.task.trim()) {
      nextErrors.task = "Task is required.";
    }
    if (!formData.response.trim()) {
      nextErrors.response = "Response format is required.";
    }
    if (formData.if_task_need_data && !formData.data.trim()) {
      nextErrors.data = "Data is required when additional data is needed.";
    }
    if (!formData.keywords_used_for_search.length) {
      nextErrors.keywords = "Add at least one keyword.";
    }
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    if (validate()) {
      onSubmit({
        ...formData,
        keywords_used_for_search: formData.keywords_used_for_search.map((item) => item.trim()),
      });
    }
  };

  const handleAddKeyword = () => {
    const keyword = newKeyword.trim();
    if (!keyword) {
      return;
    }
    if (formData.keywords_used_for_search.includes(keyword)) {
      return;
    }
    setFormData((prev) => ({
      ...prev,
      keywords_used_for_search: [...prev.keywords_used_for_search, keyword],
    }));
    setNewKeyword("");
    setErrors((prev) => ({ ...prev, keywords: undefined }));
  };

  const handleRemoveKeyword = (index) => {
    setFormData((prev) => ({
      ...prev,
      keywords_used_for_search: prev.keywords_used_for_search.filter((_, i) => i !== index),
    }));
  };

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between border-b border-gray-200 pb-4">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">
            {prompt ? "Edit Prompt" : "Create Prompt"}
          </h2>
          <p className="text-sm text-gray-600">
            Define the persona, task, and response guidance for the assistant.
          </p>
        </div>
        <button
          type="button"
          onClick={onCancel}
          className="border-2 border-black p-2 transition-colors hover:bg-red-50"
          aria-label="Close prompt form"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-semibold text-gray-900">
            Persona <span className="text-primary">*</span>
          </label>
          <input
            type="text"
            value={formData.persona}
            onChange={(event) =>
              setFormData((prev) => ({ ...prev, persona: event.target.value }))
            }
            className={`mt-2 w-full border-2 px-3 py-2 ${
              errors.persona ? "border-primary" : "border-black"
            } focus:outline-none focus:ring-2 focus:ring-primary-light`}
            placeholder="e.g., Senior Risk Analyst"
          />
          {errors.persona && <p className="mt-1 text-sm text-primary">{errors.persona}</p>}
        </div>

        <div>
          <label className="block text-sm font-semibold text-gray-900">
            Task <span className="text-primary">*</span>
          </label>
          <textarea
            value={formData.task}
            onChange={(event) =>
              setFormData((prev) => ({ ...prev, task: event.target.value }))
            }
            rows={3}
            className={`mt-2 w-full border-2 px-3 py-2 ${
              errors.task ? "border-primary" : "border-black"
            } focus:outline-none focus:ring-2 focus:ring-primary-light`}
            placeholder="Describe the task this prompt should accomplish."
          />
          {errors.task && <p className="mt-1 text-sm text-primary">{errors.task}</p>}
        </div>

        <div>
          <label className="flex items-center gap-2 text-sm font-semibold text-gray-900">
            <input
              type="checkbox"
              checked={formData.if_task_need_data}
              onChange={(event) =>
                setFormData((prev) => ({
                  ...prev,
                  if_task_need_data: event.target.checked,
                  data: event.target.checked ? prev.data : "",
                }))
              }
              className="h-4 w-4 border-2 border-black accent-primary"
            />
            Task requires additional data input
          </label>
        </div>

        {formData.if_task_need_data && (
          <div>
            <label className="block text-sm font-semibold text-gray-900">
              Data Format / Example <span className="text-primary">*</span>
            </label>
            <textarea
              value={formData.data}
              onChange={(event) =>
                setFormData((prev) => ({ ...prev, data: event.target.value }))
              }
              rows={3}
              className={`mt-2 w-full border-2 px-3 py-2 ${
                errors.data ? "border-primary" : "border-black"
              } focus:outline-none focus:ring-2 focus:ring-primary-light`}
              placeholder="Describe or provide an example of the required data format."
            />
            {errors.data && <p className="mt-1 text-sm text-primary">{errors.data}</p>}
          </div>
        )}

        <div>
          <label className="block text-sm font-semibold text-gray-900">
            Expected Response Format <span className="text-primary">*</span>
          </label>
          <textarea
            value={formData.response}
            onChange={(event) =>
              setFormData((prev) => ({ ...prev, response: event.target.value }))
            }
            rows={3}
            className={`mt-2 w-full border-2 px-3 py-2 ${
              errors.response ? "border-primary" : "border-black"
            } focus:outline-none focus:ring-2 focus:ring-primary-light`}
            placeholder="Explain how the assistant should structure its response."
          />
          {errors.response && <p className="mt-1 text-sm text-primary">{errors.response}</p>}
        </div>

        <div>
          <label className="block text-sm font-semibold text-gray-900">
            Keywords for Search <span className="text-primary">*</span>
          </label>
          <div className="mt-2 flex gap-2">
            <input
              type="text"
              value={newKeyword}
              onChange={(event) => setNewKeyword(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  handleAddKeyword();
                }
              }}
              className="flex-1 border-2 border-black px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-light"
              placeholder="Add keyword"
            />
            <button
              type="button"
              onClick={handleAddKeyword}
              className="border-2 border-black bg-primary px-3 py-2 text-white transition hover:bg-primary-dark"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>
          {errors.keywords && <p className="mt-1 text-sm text-primary">{errors.keywords}</p>}
          <div className="mt-2 flex flex-wrap gap-2">
            {formData.keywords_used_for_search.map((keyword, index) => (
              <div
                key={keyword}
                className="flex items-center gap-2 border-2 border-black bg-gray-50 px-3 py-1 text-sm text-gray-800"
              >
                <span>{keyword}</span>
                <button
                  type="button"
                  onClick={() => handleRemoveKeyword(index)}
                  className="text-primary transition-colors hover:text-primary-dark"
                  aria-label={`Remove keyword ${keyword}`}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        </div>

        <div className="flex gap-3 border-t border-gray-200 pt-4">
          <button
            type="submit"
            className="flex-1 border-2 border-black bg-primary px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-primary-dark"
          >
            {prompt ? "Update Prompt" : "Create Prompt"}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="border-2 border-black px-6 py-3 text-sm font-semibold text-gray-900 transition-colors hover:bg-gray-100"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
