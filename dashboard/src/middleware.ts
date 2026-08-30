import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  // Fix B2: Prevent LAN access to unauthenticated proxy across all dashboard routes
  const clientIp = request.headers.get("x-forwarded-for") || request.headers.get("x-real-ip") || "127.0.0.1";
  const isLocal = clientIp.includes("127.0.0.1") || clientIp.includes("::1") || clientIp.includes("localhost");
  
  if (!isLocal && request.nextUrl.pathname.startsWith("/api/scp/")) {
    return NextResponse.json(
      { error: "Access denied. Dashboard API is restricted to localhost." },
      { status: 403 }
    );
  }
  
  return NextResponse.next();
}

export const config = {
  matcher: "/api/scp/:path*",
};
