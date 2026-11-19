export default function DiffView({ before, after, diff }: { before: string; after: string; diff: string }) {
  return (
    <div>
      <div className="grid gap-3 md:grid-cols-2">
        <pre className="overflow-auto rounded-lg border border-bug/30 bg-bug/10 p-3 font-mono text-xs leading-5">{before}</pre>
        <pre className="overflow-auto rounded-lg border border-fixed/30 bg-fixed/10 p-3 font-mono text-xs leading-5">{after}</pre>
      </div>
      <pre className="mt-3 overflow-auto rounded-2xl border border-line bg-cream p-3 font-mono text-xs leading-5 text-mist">{diff}</pre>
    </div>
  );
}
