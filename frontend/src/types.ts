export type Severity = "critical" | "high" | "medium" | "low";

export interface TreeNode {
  name: string;
  type: "file" | "dir";
  path?: string;
  language?: string;
  bytes?: number;
  children?: TreeNode[];
}

export interface Project {
  id: string;
  name: string;
  source_type: string;
  sample_id: string | null;
  github_url: string | null;
  file_count: number;
  languages: { name: string; files: number }[];
  dependencies: { name: string; source: string }[];
  important: { path: string; reason: string }[];
  graph: { nodes: { id: string; kind: string }[]; edges: { from: string; to: string; kind: string }[] };
  tree: TreeNode[];
}

export interface Patch {
  id: string;
  bug_id: string;
  file: string;
  diff: string;
  before_code: string;
  after_code: string;
  status: string;
  source: string;
  confidence: number;
}

export interface Bug {
  id: string;
  scan_id: string;
  bug_details: {
    title: string;
    description: string;
    file: string;
    line: number;
    symbol: string;
    category: string;
    snippet: string;
    source: string;
    rule_id: string;
    demo_cache_used: boolean;
    cached_root_cause: string;
  };
  root_cause: string;
  trigger: string;
  student_explanation: string;
  explanation_kn: string;
  explanation_hi: string;
  suggested_patch: Patch[];
  test_results: { id: string; status: string; for_this_bug: { passed?: boolean }[] }[];
  severity_and_confidence: {
    severity: Severity;
    confidence: number;
    impact: string;
    needs_human_review: boolean;
  };
  change_history: { kind: string; message: string; at: string }[];
}

export interface Scan {
  id: string;
  project_id: string;
  status: string;
  mode: string;
  error: string;
  tool_notes: string[];
  bugs: Bug[];
}

export interface SampleInfo {
  id: string;
  title: string;
  blurb: string;
  bugs: number;
}
