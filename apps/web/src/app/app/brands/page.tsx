import { BrandKitProduct } from "@/components/brand-kit/brand-kit";
import { getBrandKitBootstrap } from "@/lib/brand-kit/brand-kit-server";

export const dynamic = "force-dynamic";

export default function BrandsPage() {
  return <BrandKitProduct bootstrap={getBrandKitBootstrap()} />;
}
