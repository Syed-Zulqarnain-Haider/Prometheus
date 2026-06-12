import {
  Activity,
  AppWindow,
  BarChart3,
  FileText,
  LayoutDashboard,
  type LucideIcon,
  Megaphone,
  Shield,
  Store,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

/** Sidebar navigation — routes per the build-order pages. */
export const NAV_ITEMS: NavItem[] = [
  { href: "/overview", label: "Executive Overview", icon: LayoutDashboard },
  { href: "/revenue", label: "Revenue", icon: BarChart3 },
  { href: "/ua", label: "UA / Marketing", icon: Megaphone },
  { href: "/store", label: "Store", icon: Store },
  { href: "/apps", label: "Apps Explorer", icon: AppWindow },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/admin", label: "Admin", icon: Shield },
  { href: "/data-health", label: "Data Health", icon: Activity },
];
