import { redirect } from "next/navigation";

// proxy.ts routes "/" to /dashboard or /login. This is the fallback if the proxy is bypassed.
export default function Home() {
  redirect("/dashboard");
}
