"use client";

import { PraticheForCustomersPanel } from "@/components/pratiche-for-customers-panel";

/** "Miei Clienti": the promoter's CRM, where they activate contracts for new
    customers (registered with their own login, see
    network/service.py::create_recruited_customer) or existing ones through
    the customer's pratica wizard. Shared with the admin "Nuovo Contratto". */
export function NetworkCustomersPanel() {
  return <PraticheForCustomersPanel mode="promoter" />;
}
