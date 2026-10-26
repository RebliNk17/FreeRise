"use client";

import { AccountCard } from "../AccountCard";
import { SettingsScreen } from "../parts";

export default function AccountSettingsPage() {
  return <SettingsScreen title="החשבון שלי">{(_s, _p, flash) => <AccountCard onChanged={() => flash("הסיסמה שונתה")} />}</SettingsScreen>;
}
