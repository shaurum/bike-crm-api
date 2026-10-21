"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Пользователи переехали в Настройки → вкладка «Пользователи». */
export default function UsersPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/settings?tab=users");
  }, [router]);

  return null;
}
