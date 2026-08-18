import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

export function proxy(request: NextRequest) {
  if (request.nextUrl.pathname !== "/projects") return NextResponse.next();
  return NextResponse.redirect(new URL("/projects/dashboard", request.url));
}

export const config = {
  matcher: ["/projects"],
};
