import { MemoView } from "@/components/memo/memo-view";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <MemoView id={id} />;
}
