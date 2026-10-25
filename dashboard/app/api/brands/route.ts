import { NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import type { Brand } from "@/lib/types";

export const revalidate = 60;

export async function GET(req: Request) {
  try {
    const url = new URL(req.url);
    const niche = url.searchParams.get("niche");
    const q = url.searchParams.get("q")?.toLowerCase();
    const sort = url.searchParams.get("sort") || "score";
    const limit = Math.min(parseInt(url.searchParams.get("limit") || "200", 10), 500);

    const db = await getDb();
    const filter: Record<string, unknown> = {};
    if (niche && niche !== "all") filter.niche = niche;
    if (q) {
      filter.$or = [
        { name: { $regex: q, $options: "i" } },
        { domain: { $regex: q, $options: "i" } },
        { niche: { $regex: q, $options: "i" } },
        { sub_niche: { $regex: q, $options: "i" } },
      ];
    }
    const sortSpec: Record<string, 1 | -1> = {};
    if (sort === "score") sortSpec.score = -1;
    else if (sort === "name") sortSpec.name = 1;
    else if (sort === "recent") sortSpec.updated_at = -1;
    else sortSpec.score = -1;

    const docs = await db
      .collection<Brand>("brands")
      .find(filter)
      .sort(sortSpec)
      .limit(limit)
      .toArray();

    return NextResponse.json({ brands: docs, count: docs.length });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}