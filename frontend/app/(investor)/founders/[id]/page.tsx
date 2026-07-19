import { FounderProfile } from "@/components/founder/founder-profile";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <FounderProfile id={id} />;
}
