"use client";

interface PipelineVisualizationProps {
  pipelineStatus: string;
}

export default function PipelineVisualization({
  pipelineStatus,
}: PipelineVisualizationProps) {
  const isRunning = pipelineStatus === "running";

  const nodes = [
    {
      label: "Postgres",
      sublabel: "Source DB",
      icon: "🐘",
      color: "from-blue-500/20 to-blue-600/20",
      border: "border-blue-500/30",
      glow: "shadow-blue-500/10",
    },
    {
      label: "WAL Stream",
      sublabel: "wal2json",
      icon: "📡",
      color: "from-amber-500/20 to-amber-600/20",
      border: "border-amber-500/30",
      glow: "shadow-amber-500/10",
    },
    {
      label: "CDC Worker",
      sublabel: "Python",
      icon: "⚙️",
      color: "from-violet-500/20 to-violet-600/20",
      border: "border-violet-500/30",
      glow: "shadow-violet-500/10",
    },
    {
      label: "ClickHouse",
      sublabel: "Analytics",
      icon: "🏠",
      color: "from-emerald-500/20 to-emerald-600/20",
      border: "border-emerald-500/30",
      glow: "shadow-emerald-500/10",
    },
  ];

  return (
    <div className="glass-card p-6">
      <div className="flex items-center gap-3 mb-5">
        <div
          className={`w-2.5 h-2.5 rounded-full ${
            isRunning ? "bg-emerald-400 animate-pulse" : "bg-red-400"
          }`}
        />
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          Pipeline
        </h2>
        <span
          className={`ml-auto text-xs font-medium px-2.5 py-1 rounded-full ${
            isRunning
              ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
              : "bg-red-500/15 text-red-400 border border-red-500/30"
          }`}
        >
          {isRunning ? "STREAMING" : pipelineStatus.toUpperCase()}
        </span>
      </div>

      <div className="flex items-center justify-between gap-2">
        {nodes.map((node, i) => (
          <div key={node.label} className="flex items-center gap-2 flex-1">
            {/* Node */}
            <div
              className={`
                flex-1 glass-card glass-card-hover p-4 text-center
                bg-gradient-to-br ${node.color} ${node.border}
                ${isRunning ? `shadow-lg ${node.glow}` : ""}
              `}
            >
              <div className="text-2xl mb-1.5">{node.icon}</div>
              <div className="text-sm font-semibold text-gray-200">
                {node.label}
              </div>
              <div className="text-[11px] text-gray-500 mt-0.5">
                {node.sublabel}
              </div>
            </div>

            {/* Arrow connector */}
            {i < nodes.length - 1 && (
              <div className="flex-shrink-0 w-8 flex items-center justify-center">
                <div className="relative w-full h-[2px] bg-gray-700/50 overflow-hidden rounded-full">
                  {isRunning && (
                    <div
                      className="absolute inset-y-0 w-3 bg-gradient-to-r from-transparent via-indigo-400 to-transparent animate-data-flow"
                      style={{ animationDelay: `${i * 0.4}s` }}
                    />
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
