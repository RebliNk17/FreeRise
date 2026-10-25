"use client";

import { NotificationList, ReadAllButton, useNotifications } from "@/components/NotificationBell";

/** Every notification. Reached only from the bell sheet's "הצגת כל ההתראות", not the menu. */
export default function NotificationsPage() {
  const n = useNotifications(500); // the API's max
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <h1 className="page-title flex-1">התראות</h1>
        <ReadAllButton {...n} />
      </div>
      <NotificationList {...n} />
    </div>
  );
}
