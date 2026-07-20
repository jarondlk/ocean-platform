import { redirect } from "next/navigation";

export default function EvidenceRedirectPage() {
  redirect("/explore?view=evidence");
}
