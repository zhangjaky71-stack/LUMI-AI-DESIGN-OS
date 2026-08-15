import { redirect } from "next/navigation";
import { AdminConsole } from "@/components/admin-console/admin-console";
import { requireShellSession } from "@/lib/app-shell/auth-server";
import { getAdminBootstrap } from "@/lib/admin-console/admin-server";

export default async function AdminPage() {
  const session = await requireShellSession();
  if (!session.platform_admin) redirect("/app/projects?reason=platform-admin-required");
  return <AdminConsole bootstrap={getAdminBootstrap(session.platform_admin)} />;
}
