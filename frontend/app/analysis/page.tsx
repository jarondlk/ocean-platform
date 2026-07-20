import { redirect } from "next/navigation";

export default function AnalysisRedirectPage() {
  redirect("/data?view=analysis");
}
