import type { TreeNode } from "../types";

export default function FileTree({ nodes }: { nodes: TreeNode[] }) {
  return (
    <ul className="space-y-1 text-sm">
      {nodes.map((node) => (
        <li key={node.path || node.name}>
          {node.type === "dir" ? (
            <details open>
              <summary className="cursor-pointer text-mist">{node.name}/</summary>
              <div className="ml-4 mt-1">
                <FileTree nodes={node.children || []} />
              </div>
            </details>
          ) : (
            <span>
              {node.name} <span className="text-mist">{node.language}</span>
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
