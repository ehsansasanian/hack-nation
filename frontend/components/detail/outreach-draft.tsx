import { Send } from "lucide-react";

export function OutreachDraft({ text }: { text: string }) {
  return (
    <section className="rounded-xl border border-blue-200 bg-blue-50/50 p-4">
      <div className="mb-2 flex items-center gap-2">
        <Send className="size-4 text-blue-700" />
        <h2 className="text-sm font-semibold text-blue-900">Outreach message</h2>
        <span className="rounded border border-amber-300 bg-amber-100 px-1.5 py-0.5 text-[0.7rem] font-semibold uppercase tracking-wide text-amber-800">
          Draft · never sent
        </span>
      </div>
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap font-sans text-sm leading-relaxed text-foreground/90">
        {text}
      </pre>
    </section>
  );
}
