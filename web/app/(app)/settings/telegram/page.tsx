"use client";

import { SettingsScreen } from "../parts";
import { TelegramCard } from "../TelegramCard";

export default function TelegramSettingsPage() {
  return <SettingsScreen title="טלגרם">{(data, patch) => <TelegramCard settings={data} patch={patch} />}</SettingsScreen>;
}
