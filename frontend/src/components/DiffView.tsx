export default function DiffView({ before, after, diff }: { before: string; after: string; diff: string }) {
  return (
    <div>
      <div className="grid gap-3 md:grid-cols-2">
        <pre className="overflow-auto rounded-lg border border-coral/40 bg-coral/10 p-3 font-mono text-xs leading-5">{before}</pre>
        <pre className="overflow-auto rounded-lg border border-good/40 bg-good/10 p-3 font-mono text-xs leading-5">{after}</pre>
      </div>
      <pre className="mt-3 overflow-auto rounded-lg border border-line bg-ink p-3 font-mono text-xs leading-5 text-mist">{diff}</pre>
    </div>
  );
}
