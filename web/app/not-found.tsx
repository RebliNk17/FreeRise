import Link from "next/link";
import { SunHorizon } from "@/components/Logo";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col items-center justify-center gap-4 px-4 text-center">
      <SunHorizon width={150} />
      <h1 className="page-title">העמוד לא נמצא</h1>
      <Link href="/home" className="btn">
        חזרה לדף הבית
      </Link>
    </main>
  );
}
