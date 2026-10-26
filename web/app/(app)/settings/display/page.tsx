"use client";

import { ThemeToggle } from "@/components/ThemeToggle";
import { Section, SubHeader } from "../parts";

export default function DisplaySettingsPage() {
  return (
    <div className="flex flex-col gap-4">
      <SubHeader title="תצוגה" />
      <Section id="display">
        <ThemeToggle />
      </Section>
    </div>
  );
}
