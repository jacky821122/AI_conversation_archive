import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import Markdown from "../components/Markdown";
import { Loading, ErrorBox } from "./Dashboard";

export default function Plan() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["plan"],
    queryFn: api.plan,
  });

  if (isLoading) return <Loading />;
  if (error) return <ErrorBox msg={String(error)} />;
  if (!data) return null;

  if (!data.exists) {
    return (
      <div className="space-y-4">
        <h1 className="font-display text-2xl font-semibold text-ink">計畫</h1>
        <p className="max-w-xl font-mono text-xs leading-relaxed text-muted">
          本機沒有 <code>PLAN.local.md</code>。它是 gitignored 的本機進度檔，
          只在主要開發機上存在；其他 clone 不會有這個檔。
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="font-display text-2xl font-semibold text-ink">計畫</h1>
      <Markdown>{data.content}</Markdown>
    </div>
  );
}
