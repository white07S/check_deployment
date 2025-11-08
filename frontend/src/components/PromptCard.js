import {
  Copy,
  Database,
  Edit2,
  FileText,
  Hash,
  MessageSquare,
  Play,
  Trash2,
  User,
  UserCircle,
  Calendar,
} from "lucide-react";

function formatDate(value) {
  if (!value) {
    return "Unknown";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Unknown";
  }
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function PromptCard({ prompt, onSelect, onEdit, onCopy, onDelete, isOwner }) {
  const {
    persona,
    task,
    if_task_need_data: requiresData,
    data,
    response,
    keywords_used_for_search: keywords = [],
    user_id: owner,
    created_at: createdAt,
    response_preview: responsePreview,
  } = prompt;

  return (
    <div className="border-2 border-black bg-white transition-shadow hover:shadow-lg">
      <div className="p-4 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 space-y-1">
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-900">
              <User className="h-4 w-4 text-gray-600" />
              <span>{persona}</span>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-xs text-gray-600">
              <div className="flex items-center gap-1">
                <UserCircle className="h-3 w-3" />
                <span>{owner || "Anonymous"}</span>
              </div>
              <div className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                <span>{formatDate(createdAt)}</span>
              </div>
              {isOwner && (
                <span className="border border-black bg-primary px-2 py-0.5 text-white text-xs">
                  Your Prompt
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-2 text-sm text-gray-800">
          <p>
            <strong>Task:</strong> {task}
          </p>
          {requiresData && (
            <div className="flex items-center gap-1 text-xs text-gray-600">
              <Database className="h-3 w-3" />
              <span>Requires data input</span>
            </div>
          )}
        </div>

        <div>
          <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-gray-600">
            <MessageSquare className="h-3 w-3" />
            <span>Response:</span>
          </div>
          <p className="text-sm text-gray-700 whitespace-pre-line">{response || responsePreview}</p>
        </div>

        {data && (
          <div>
            <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-gray-600">
              <FileText className="h-3 w-3" />
              <span>Data Template:</span>
            </div>
            <p className="border border-gray-200 bg-gray-50 p-2 text-sm text-gray-700 whitespace-pre-wrap">
              {data}
            </p>
          </div>
        )}

        <div>
          <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-gray-600">
            <Hash className="h-3 w-3" />
            <span>Keywords:</span>
          </div>
          <div className="flex flex-wrap gap-1">
            {keywords.length === 0 ? (
              <span className="text-xs text-gray-500">No keywords</span>
            ) : (
              keywords.map((keyword, index) => (
                <span key={index} className="px-2 py-1 text-xs border border-gray-300 bg-gray-50">
                  {keyword}
                </span>
              ))
            )}
          </div>
        </div>

        <div className="flex gap-2 border-t border-gray-200 pt-3">
          <button
            type="button"
            onClick={onSelect}
            className="flex flex-1 items-center justify-center gap-1 border-2 border-black bg-primary px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-dark"
          >
            <Play className="h-3 w-3" />
            Use
          </button>
          {isOwner && (
            <button
              type="button"
              onClick={onEdit}
              className="border-2 border-gray-300 px-3 py-2 text-xs transition-colors hover:border-black"
              title="Edit"
            >
              <Edit2 className="h-3 w-3" />
            </button>
          )}
          <button
            type="button"
            onClick={onCopy}
            className="border-2 border-gray-300 px-3 py-2 text-xs transition-colors hover:border-black"
            title="Copy"
          >
            <Copy className="h-3 w-3" />
          </button>
          {isOwner && (
            <button
              type="button"
              onClick={onDelete}
              className="border-2 border-red-300 px-3 py-2 text-xs text-red-600 transition-colors hover:border-red-600"
              title="Delete"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
