"use client";

import { useSearchParams } from "next/navigation";

export function HomeNotice() {
  const params = useSearchParams();
  if (params.get("aviso") !== "conta-eliminada") return null;
  return (
    <p role="status" className="notice">
      A sua conta e os dados associados foram eliminados.
    </p>
  );
}
