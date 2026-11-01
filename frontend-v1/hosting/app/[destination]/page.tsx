import { notFound } from "next/navigation";
import { HostPage } from "../host-page";
export const dynamic = "force-dynamic";
export default async function Page({ params }: { params: Promise<{ destination: string }> }) {
  const { destination } = await params;
  if (destination !== "admin" && destination !== "about" && destination !== "feedback") notFound();
  return <HostPage destination={destination} />;
}
